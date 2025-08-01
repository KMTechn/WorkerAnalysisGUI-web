# 🚀 서버 배포 가이드 (Server Deployment Guide)

이 문서는 `WorkerAnalysisGUI-web` 프로젝트를 지정된 서버에 자동으로 배포하기 위한 설정 과정을 안내합니다. GitHub Actions를 사용하여 `main` 브랜치에 코드가 푸시될 때마다 서버의 내용이 자동으로 업데이트됩니다.

## 목차
1. [사전 준비 사항](#1-사전-준비-사항)
2. [1단계: 서버 환경 준비](#2-1단계-서버-환경-준비)
3. [2단계: 배포용 SSH 키 생성 및 등록](#3-2단계-배포용-ssh-키-생성-및-등록)
4. [3단계: 프로젝트 클론 및 초기 설정](#4-3단계-프로젝트-클론-및-초기-설정)
5. [4단계: GitHub Repository 설정](#5-4단계-github-repository-설정)
6. [5단계: GitHub Actions 워크플로우 활성화](#6-5단계-github-actions-워크플로우-활성화)
7. [배포 확인 및 문제 해결](#7-배포-확인-및-문제-해결)

---

## 1. 사전 준비 사항
- 배포를 진행할 Linux 서버 (Ubuntu 20.04 이상 권장)
- 서버의 `sudo` 권한을 가진 계정
- GitHub Repository의 관리자(Admin) 또는 소유자(Owner) 권한

---

## 2. 1단계: 서버 환경 준비

배포 자동화를 위해 서버에 Git, Python 등을 설치하고 배포 전용 사용자를 생성합니다.

### 2.1. 배포 전용 사용자 생성 (권장)
보안을 위해 `root`가 아닌 별도의 사용자로 배포를 진행합니다.
```bash
# 'deployer'라는 이름의 새로운 사용자를 생성합니다.
sudo adduser deployer

# 생성한 사용자에게 sudo 권한을 부여합니다.
sudo usermod -aG sudo deployer

# deployer 사용자로 전환합니다.
su - deployer
```

### 2.2. 필수 패키지 설치
`deployer` 사용자로 접속된 상태에서 다음 패키지를 설치합니다.
```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-pip python3-venv
```

---

## 3. 2단계: 배포용 SSH 키 생성 및 등록

GitHub Actions가 비밀번호 없이 서버에 접속하려면 SSH 키를 사용해야 합니다.

### 3.1. SSH 키 페어 생성
`deployer` 사용자의 홈 디렉토리에서 다음 명령어를 실행합니다.
```bash
# ~/.ssh 디렉토리로 이동 (없으면 생성)
mkdir -p ~/.ssh && cd ~/.ssh

# SSH 키를 생성합니다. 비밀번호(passphrase)는 입력하지 않고 Enter를 누릅니다.
# 키 이름은 id_rsa_github_actions 로 지정합니다.
ssh-keygen -t rsa -b 4096 -C "github-actions-deploy" -f id_rsa_github_actions
```

### 3.2. 공개 키 등록
생성��� 공개 키(`id_rsa_github_actions.pub`)를 서버가 신뢰하는 키 목록(`authorized_keys`)에 추가합니다.
```bash
# 공개 키 내용을 authorized_keys 파일에 추가합니다.
cat ~/.ssh/id_rsa_github_actions.pub >> ~/.ssh/authorized_keys

# 보안을 위해 .ssh 디렉토리와 파일의 권한을 설정합니다.
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

### 3.3. 개인 키 확인
**이 키는 절대로 외부에 노출되면 안 됩니다.** GitHub Secrets에 등록하기 위해 내용을 복사합니다.
```bash
# 개인 키의 내용을 출력합니다. 이 내용을 복사해두세요.
cat ~/.ssh/id_rsa_github_actions
```
> 출력된 `-----BEGIN OPENSSH PRIVATE KEY-----` 부터 `-----END OPENSSH PRIVATE KEY-----` 까지의 모든 내용을 복사합니다.

---

## 4. 3단계: 프로젝트 클론 및 초기 설정

`deployer` 사용자로 프로젝트를 클론하고, 실행에 필요한 가상 환경을 설정합니다.

```bash
# deployer 사용자의 홈 디렉토리로 이동합니다.
cd ~

# GitHub 저장소를 클론합니다.
git clone https://github.com/KMTechn/WorkerAnalysisGUI-web.git

# 프로젝트 디렉토리로 이동합니다.
cd WorkerAnalysisGUI-web

# Python 가상 환경을 생성합니다.
python3 -m venv venv

# 가상 환경을 활성화합니다.
source venv/bin/activate

# 필요한 라이브러리를 설치하여 환경을 테스트합니다.
pip install -r requirements.txt

# 가상 환경을 비활성화합니다.
deactivate
```
> **중요:** 현재 프로젝트의 절대 경로를 확인해두세요. `pwd` 명령어로 확인할 수 있습니다. (예: `/home/deployer/WorkerAnalysisGUI-web`)

---

## 5. 4단계: GitHub Repository 설정

GitHub Actions가 서버에 접속할 수 있도록, 복사해둔 개인 키와 서버 정보를 GitHub Repository의 Secrets에 등록합니다.

1.  프로젝트 GitHub Repository 페이지로 이동합니다.
2.  `Settings` > `Secrets and variables` > `Actions` 메뉴로 이동합니다.
3.  `New repository secret` 버튼을 클릭하여 아래 3개의 Secret을 추가합니다.

| Secret 이름         | 값 (Value)                                                              | 설명                               |
| ------------------- | ----------------------------------------------------------------------- | ---------------------------------- |
| `SERVER_HOST`       | 서버의 IP 주소 또는 도메인 이름                                         | 예: `123.123.123.123`              |
| `SERVER_USERNAME`   | 2.1 단계에서 생성한 사용자 이름                                         | 예: `deployer`                     |
| `SSH_PRIVATE_KEY`   | 3.3 단계에서 복사한 **개인 키**의 전체 내용                             | `-----BEGIN...` 부터 `...END-----` 까지 |

---

## 6. 5단계: GitHub Actions 워크플로우 활성화

마지막으로, 비활성화했던 배포 워크플로우를 다시 활성화하고 서버 경로를 수정합니다.

1.  로컬 PC의 프로젝트에서 `.github/workflows/deploy.yml` 파일을 엽니다.
2.  파일 내용을 아래와 같이 수정합니다.
    -   `if: false` 라인을 **삭제**합니다.
    -   `cd` 명령어의 경로를 **4단계에서 확인한 실제 서버 경로**로 변경합니다.

    ```yaml
    # .github/workflows/deploy.yml

    name: Deploy to Server

    on:
      push:
        branches:
          - main

    jobs:
      deploy:
        # if: false  <- 이 라인을 삭제하세요.
        runs-on: ubuntu-latest
        steps:
        - name: Checkout code
          uses: actions/checkout@v3

        - name: Deploy to server
          uses: appleboy/ssh-action@master
          with:
            host: ${{ secrets.SERVER_HOST }}
            username: ${{ secrets.SERVER_USERNAME }}
            key: ${{ secrets.SSH_PRIVATE_KEY }}
            script: |
              # 프로젝트 디렉토리로 이동 (실제 서버 경로로 수정 필수!)
              cd /home/deployer/WorkerAnalysisGUI-web 
              
              # 배포 스크립트 실행
              bash deploy.sh
    ```

3.  수정된 `deploy.yml` 파일을 커밋하고 `main` 브랜치에 푸시합니다.
    ```bash
    git add .github/workflows/deploy.yml
    git commit -m "feat(ci): Enable server deployment workflow"
    git push origin main
    ```

---

## 7. 배포 확인 및 문제 해결

-   **GitHub Actions 확인**: 푸시 후 Repository의 `Actions` 탭에서 `Deploy to Server` 워크플로우가 성공적으로 실행되었는지 확인합니다.
-   **서버 확인**: `deployer` 사용자로 서버에 접속하여 `WorkerAnalysisGUI-web` 디렉토리로 이동한 후, 아래 파일들이 생성/업데이트되었는지 확인합니다.
    -   `server.log`: `app.py` 실행 로그
    -   `app.pid`: 실행 중인 `app.py` 프로세스 ID
-   **프로세스 확인**: `ps aux | grep app.py` 명령어로 파이썬 앱이 실행 중인지 확인합니다.
-   **문제 발생 시**: GitHub Actions의 로그를 확인하여 어느 단계에서 오류가 발생했는지 파악하는 것이 가장 중요합니다. (SSH 접속 실패, `cd` 경로 오류, `pip install` 실패 등)
