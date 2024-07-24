import socketserver
import os
import threading
import time
import shutil
import zipfile
import tempfile

import docker
import flask

###########
# Backend #
###########

def parse_job_options(input_data):
    valid_options = ["REPO_A", "REPO_B", "COMMIT_A", "COMMIT_B"]
    options = {}

    for line in input_data.readlines():
        line = line.strip()

        # Stop on the first line that is not a command
        if line[0] != "#":
            break

        splits = line.split(' ')
        if len(splits) == 2 and splits[0] in valid_options:
            options[splits[0]] = splits[1]

    return options


class Backend:
    def __init__(self):
        self.image = "ghcr.io/acts-project/ubuntu2404:53"
        self.client = docker.from_env()
        self.jobs = {}

    def run_docker_job(self, job_id, input_data):
        with tempfile.TemporaryDirectory() as job_dir:
            env_vars = parse_job_options(input_data)

            input_file = os.path.join(job_dir, "script.py")
            with open(input_file, 'wb') as f:
                f.write(input_data)

            shutil.copyfile("run.sh", os.path.join(job_dir, "run.sh"))

            log_file = os.path.join(job_dir, "log.txt")

            container = self.client.containers.run(
                self.image,
                volumes={job_dir: {'bind': '/job', 'mode': 'rw'}},
                working_dir="/job",
                detach=True,
                command=f"sh -c './run.sh 2>&1 > /job/log.txt'",
                environment=env_vars
            )

            self.jobs[job_id]['status'] = 'running'

            while container.status != 'exited':
                container.reload()
                if os.path.exists(log_file):
                    with open(log_file, 'r') as log:
                        logs = log.readlines()
                        if logs:
                            progress = logs[-1].strip()
                            self.jobs[job_id]['progress'] = progress
                time.sleep(1)

            result = container.wait()

            output_file = os.path.join(job_dir, "output.txt")
            zip_file = os.path.join(job_dir, "output.zip")
            with zipfile.ZipFile(zip_file, 'w') as zipf:
                for root, dirs, files in os.walk(job_dir):
                    for file in files:
                        zipf.write(os.path.join(root, file), file)

            self.jobs[job_id]['zip_file'] = zip_file
            self.jobs[job_id]['status'] = 'completed'
            self.jobs[job_id]['exit_code'] = result['StatusCode']

backend = Backend()

##############
# TCP server #
##############

class RequestHandler(socketserver.StreamRequestHandler):
    def handle(self):
        input_data = self.rfile.read().decode("utf-8")

        job_id = str(int(time.time()))
        backend.jobs[job_id] = {'status': 'pending', 'progress': '', 'zip_file': ''}


        self.wfile.write(f"http://localhost:5000/status/{job_id}".encode('utf-8'))

        thread = threading.Thread(target=backend.run_docker_job, args=(job_id, input_data))
        thread.start()


def start_tcp_server(host, port):
    print(f"Start TCP server on {host}:{port}")

    server = socketserver.TCPServer((host, port), RequestHandler)
    server.serve_forever()


##############
# Web Server #
##############

webserver = flask.Flask(__name__)

@app.route('/status/<job_id>', methods=['GET'])
def job_status(job_id):
    if job_id not in backend.jobs:
        return flask.jsonify({"error": "Job not found"}), 404

    job = backend.jobs[job_id]
    return flask.jsonify({
        "status": job['status'],
        "progress": job['progress'],
        "download_url": f"/download/{job_id}"
    })

@app.route('/download/<job_id>', methods=['GET'])
def download_file(job_id):
    if job_id not in backend.jobs:
        return flask.jsonify({"error": "Job not found"}), 404

    job = backend.jobs[job_id]
    if job['status'] != 'completed':
        return flask.jsonify({"error": "Job not completed yet"}), 400

    return flask.send_file(job['zip_file'], as_attachment=True, download_name='output.zip')



def main():
    tcp_thread = threading.Thread(target=start_tcp_server, args=('0.0.0.0', 8888))
    tcp_thread.start()

    webserver.run(debug=True, port=8889)


if __name__ == "__main__":
    main()
