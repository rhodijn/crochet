pipeline {
    agent any

    environment {
        zhawRegistry = "https://nexus.zhaw.ch:5000"
    }

    options {
        skipStagesAfterUnstable()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '10', artifactNumToKeepStr: '10'))
        timeout(time: 5, unit: 'MINUTES')
    }

    stages {
        stage('Build Container image') {
          steps {
            script {
                def contImage = docker.build("hsb/<APP_NAME>")

                docker.withRegistry(zhawRegistry) {
                    contImage.push("${env.BUILD_NUMBER}")
                    contImage.push("latest")
                }
            }
          }
        }

        stage('Deploy to Kubernetes') {
          steps {
              sh "kubectl set image deploy <APP_NAME> <APP_NAME>=nexus.zhaw.ch:5000/hsb/<APP_NAME>:${env.BUILD_NUMBER} --context juju-context-mr -n <NAMESPACE>" 
          }
        }
    }
}
