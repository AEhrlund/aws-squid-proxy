- [Introduction](#introduction)
- [Getting started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Quick start](#quick-start)
- [Troubleshooting](#troubleshooting)

# Introduction
A Python script that creates or starts a AWS instance with Squid proxy that only allows connections from my external IP. Autamatically stops the AWS instance after a specified time.

# Getting started
## Prerequisites
- Python 3
- Security group, with TCP port 3128 open for inbound connection (named proxy-security-group)
- Key pair (named proxy-key)
- Private key (need to update source with the path to the .pem file)

## Quick start
- Create security group.
- Create key pair and download private key.
- Run: python awssquidproxy.py
- Done!

# Troubleshooting
- docker exec -it aws-squid-proxy tail -f /var/log/squid/access.log
- docker restart aws-squid-proxy
