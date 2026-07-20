pipeline {
  agent any
  environment {
    HARBOR = '10.10.1.163'
    IMAGE  = '10.10.1.163/flask-hello/flask-hello'
  }
  stages {
    stage('Checkout') {
      steps { checkout scm }
    }
    stage('SonarQube Analysis') {
        steps {
            script {
                def scannerHome = tool 'sonar-scanner'
                withSonarQubeEnv('sonarqube') {
                    sh "${scannerHome}/bin/sonar-scanner"
                }
            }
        }
    }

    stage('Quality Gate') {
        steps {
            timeout(time: 5, unit: 'MINUTES') {
                waitForQualityGate abortPipeline: true
            }
        }
    }
    stage('Build image') {
      steps {
        script { env.TAG = sh(script: 'git rev-parse --short HEAD', returnStdout: true).trim() }
        sh 'docker build -t $IMAGE:$TAG -t $IMAGE:latest aws-k8s-lab/flask-hello'
      }
    }
    stage('Push to Harbor') {
      steps {
        withCredentials([usernamePassword(credentialsId: 'harbor-cred',
                          usernameVariable: 'HU', passwordVariable: 'HP')]) {
          sh '''
            echo "$HP" | docker login $HARBOR -u "$HU" --password-stdin
            docker push $IMAGE:$TAG
            docker push $IMAGE:latest
          '''
        }
      }
    }
  }
}
