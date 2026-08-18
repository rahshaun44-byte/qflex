#!/bin/bash
# scaffold-qf.sh - Creates the directory structure for Quantum Flex SOC-in-a-box

QF_ROOT="/home/rahshaunchambers/quantum-flex"

echo "[+] Creating Quantum Flex directory structure at $QF_ROOT..."

mkdir -p "$QF_ROOT"/core-engine/{discovery,vuln-scanner,log-collection}
mkdir -p "$QF_ROOT"/telemetry/{suricata,zeek,opensearch}
mkdir -p "$QF_ROOT"/threat-detection/{triagewall,rules}
mkdir -p "$QF_ROOT"/ai-agents/{models,prompts}
mkdir -p "$QF_ROOT"/dashboard/{frontend,backend}

echo "Version 1 Focus: Device discovery, Vuln scanner, Log collection, Dashboard" > "$QF_ROOT"/core-engine/README.md
echo "Version 2 Focus: AI analysis, Auto-remediation, Threat intel" > "$QF_ROOT"/ai-agents/README.md
echo "Version 3 Focus: Multiple nodes, Edge computing" > "$QF_ROOT"/telemetry/README.md

echo "[+] Directory structure created successfully."
