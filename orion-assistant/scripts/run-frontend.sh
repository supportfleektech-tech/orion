#!/usr/bin/env bash
set -euo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)/frontend"
npm run dev -- --host 0.0.0.0
