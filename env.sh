#!/bin/bash
# Default configuration for the AI training lab.
# Values changed from the menu are saved in .lab-config (loaded after this file).

SIZE_LINUX='Standard_B12ms'      # 12 vCPU - 48 GB RAM (CPU only)

# 5 VMs per region (quota by region) - 20 environments max
LOCATION1='francecentral'
LOCATION2='westeurope'
LOCATION3='northeurope'
LOCATION4='uksouth'

# AI models pulled by Ollama on each VM
LLM_MODEL='qwen2.5:7b'
EMBED_MODEL='nomic-embed-text'

# Menu defaults
DOMAIN_NAME_DEFAULT='aitraining'
PASSWORD='DummyP@ssword00'
START_ENV=0
NBENV=3
OPENLLMETRY_ENABLED='N'          # Y = traces sent to Dynatrace (OpenLLMetry or OpenInference, see TELEMETRY_TYPE)
TELEMETRY_TYPE='openllmetry'     # openllmetry (default) | openinference (via an OpenTelemetry Collector)
VM_STARTED='N'                   # N = VM deallocated after installation

# Dynatrace (only used if OpenLLMetry is enabled)
MyTenant=''                      # <id>.live.dynatrace.com
MyToken=''                       # dt0c01.xxx.yyy

# LLM judge for dt-evals (trainer's shared key, available in the VS Code web of every VM)
JUDGE_PROVIDER='openai'          # openai | anthropic | gemini
JUDGE_MODEL=''                   # empty = default model of the provider
JUDGE_API_KEY=''
