import os
import time
import requests
from requests.auth import HTTPBasicAuth

JENKINS_URL = os.getenv("JENKINS_URL", "http://localhost:8080")
USER = os.getenv("JENKINS_USER", "admin")
TOKEN = os.getenv("JENKINS_TOKEN", "admin") # default for dummy setups

# Basic Jenkins Pipeline XML
JOB_XML = """<?xml version='1.1' encoding='UTF-8'?>
<flow-definition plugin="workflow-job@1316.vd2290d3341a_f">
  <actions/>
  <description>Cortex CI/CD Demo Pipeline</description>
  <keepDependencies>false</keepDependencies>
  <properties/>
  <definition class="org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition" plugin="workflow-cps@3731.ve4b_5b_857b_a_d3">
    <script>pipeline {
    agent any
    stages {
        stage(&apos;Build&apos;) {
            steps {
                echo &apos;Building...&apos;
                sleep 2
            }
        }
        stage(&apos;Test&apos;) {
            steps {
                echo &apos;Testing...&apos;
                sleep 2
            }
        }
        stage(&apos;Deploy&apos;) {
            steps {
                echo &apos;Deploying...&apos;
                sleep 2
            }
        }
    }
}</script>
    <sandbox>true</sandbox>
  </definition>
  <triggers/>
  <disabled>false</disabled>
</flow-definition>"""

def init_jenkins():
    print(f"Waiting for Jenkins at {JENKINS_URL}...")
    
    # Wait for Jenkins to be up
    for _ in range(30):
        try:
            r = requests.get(JENKINS_URL)
            if r.status_code in [200, 403]:
                print("Jenkins is reachable!")
                break
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(2)
    else:
        print("Failed to reach Jenkins.")
        return

    # In a real setup, we would need to get the Crumb first, but with runSetupWizard=false
    # and anonymous read (or basic auth), we can often just post.
    # Actually, let's just create the job directly:
    job_name = "CortexCICD_Self-Healing-CI-CD"
    
    create_url = f"{JENKINS_URL}/createItem?name={job_name}"
    headers = {"Content-Type": "application/xml"}
    
    print(f"Creating job: {job_name}")
    resp = requests.post(create_url, data=JOB_XML, headers=headers, auth=HTTPBasicAuth(USER, TOKEN))
    
    if resp.status_code == 200:
        print(f"Successfully created job {job_name}!")
    elif resp.status_code == 400 and "already exists" in resp.text:
        print(f"Job {job_name} already exists.")
    else:
        print(f"Failed to create job: {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    init_jenkins()
