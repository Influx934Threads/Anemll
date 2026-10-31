# ANEMLL Setup Notes - M3 MacBook Pro

**Date:** 2024-10-29 (Updated)
**System:** M3 MacBook Pro, 18GB RAM, macOS 15.1 (Sequoia)
**Goal:** Utilize the idle Apple Neural Engine (ANE) for LLM inference

**Context:** Already running optimized llama.cpp inference on CPU/GPU. The M3's Neural Engine (ANE) was sitting unused - ANEMLL now leverages this dedicated AI hardware.

---

## Summary

**ANE INFERENCE IS WORKING!**

After upgrading from Sonoma 14.4 to Sequoia 15.1, ANEMLL now runs successfully:

```
Model: Qwen2.5-0.5B (pre-converted, 6-bit LUT)
Prefill: 64.3 tokens/sec
Inference: 62.8 tokens/sec
Context: 2048 tokens
```

The Neural Engine is now actively running LLM inference.

---

## Post-Migration Fixes (2024-10-29)

After Sequoia upgrade, dependencies needed updating:

```bash
source env-anemll/bin/activate
pip install --upgrade torch torchvision  # 2.5.0 → 2.15.0
pip install 'transformers>=4.39.0,<5.0.0'  # 5.20.2 → 4.57.6
```

The newer transformers 5.x had breaking API changes; 4.57.6 works correctly.

---

## Quick Start (Working)

```bash
cd /Users/agundez/Build/Anemll
source env-anemll/bin/activate

# Test with pre-downloaded model
python ./tests/chat.py --meta ~/.cache/huggingface/hub/models--anemll--anemll-Qwen-Qwen2.5-0.5B-Instruct-ctx2048-monolithic_0.3.5/snapshots/4a2af987aca06f20663be1ce550a85f72aa72f03/meta.yaml
```

---

## What Was Completed

### 1. Repository Setup
- Cloned ANEMLL from https://github.com/Anemll/Anemll
- Location: `/Users/agundez/Build/Anemll`

### 2. Python Environment
- Created virtual environment: `env-anemll` (Python 3.11)
- Installed all dependencies:
  - PyTorch 2.5.0 (MPS available)
  - CoreMLTools 9.0
  - Transformers, scikit-learn, etc.

### 3. System Tools
- Installed `jq` via Homebrew
- Xcode Command Line Tools present

### 4. Models Downloaded
| Model | Location | Status |
|-------|----------|--------|
| Qwen3.5-0.8B-text-only | `~/.cache/huggingface/hub/models--principled-intelligence--Qwen3.5-0.8B-text-only/` | Incompatible architecture |
| Qwen3-0.6B | `~/.cache/huggingface/hub/models--Qwen--Qwen3-0.6B/` | Conversion failed (macOS) |
| Qwen2.5-0.5B (pre-converted) | `~/.cache/huggingface/hub/models--anemll--anemll-Qwen-Qwen2.5-0.5B-Instruct-ctx2048-monolithic_0.3.5/` | Cannot load (macOS) |

---

## What's Left To Do

Once macOS is upgraded to Sequoia (15+):

```bash
# Activate environment
cd /Users/agundez/Build/Anemll
source env-anemll/bin/activate

# Test with pre-converted model (already downloaded)
python ./tests/chat.py \
  --meta ~/.cache/huggingface/hub/models--anemll--anemll-Qwen-Qwen2.5-0.5B-Instruct-ctx2048-monolithic_0.3.5/snapshots/4a2af987aca06f20663be1ce550a85f72aa72f03/meta.yaml \
  --prompt "Hello, who are you?"

# Or convert Qwen3-0.6B from scratch
./anemll/utils/convert_model.sh \
  --model Qwen/Qwen3-0.6B \
  --output ./models/qwen3-0.6b \
  --context 512 \
  --chunk 2
```

---

## The Obstacle: macOS 15 Requirement

### Why macOS 15 (Sequoia) is Required

1. **CoreML Multi-Function Models**
   - ANEMLL models use separate `infer` and `prefill` functions
   - The `functionName` property requires macOS 15+
   - Error: `RuntimeError: The 'functionName' property can only be set on macOS >= 15.0`

2. **CoreML8 Opset**
   - CoreMLTools 9.0 generates CoreML8 format by default
   - CoreML8 parsing requires macOS 15+
   - Error: `Unknown opset 'CoreML8'`

3. **Apple's ANE Improvements**
   - macOS 15 includes significant Neural Engine enhancements
   - Better support for transformer architectures on ANE

### Current System
```
macOS Version: 14.4 (Sonoma)
Required:      15.0+ (Sequoia)
```

---

## Why ANE Matters

The M3's Neural Engine is **dedicated AI silicon** separate from CPU and GPU:

| Hardware | Current Status | With ANEMLL |
|----------|---------------|-------------|
| CPU | Used by llama.cpp | Free for other tasks |
| GPU (Metal) | Used by llama.cpp | Free for other tasks |
| **ANE** | **Idle (0% utilized)** | Runs LLM inference |

### ANE Benefits
- **Power efficiency** - ANE is optimized for sustained ML workloads
- **Parallel execution** - Run inference on ANE while GPU handles other tasks
- **Thermal headroom** - Less heat from CPU/GPU means sustained performance

---

## Model Compatibility Notes

### Tested Models

| Model | Architecture | ANEMLL Compatible |
|-------|--------------|-------------------|
| Qwen3-0.6B | Standard Qwen3 | Yes (needs macOS 15) |
| Qwen3.5-0.8B | Hybrid Mamba-Transformer | No (unsupported architecture) |
| Qwen2.5-0.5B | Standard Qwen2 | Yes (needs macOS 15) |

### Qwen3.5 Architecture Issue
Qwen3.5 uses a hybrid architecture with:
- `linear_attn` layers (Mamba-style state-space model)
- `full_attention` layers (standard transformer)

This hybrid design is not supported by ANEMLL's Qwen converter, which expects pure transformer architecture.

---

## File Structure

```
/Users/agundez/Build/Anemll/
├── env-anemll/              # Python virtual environment
├── anemll/                  # Core library
│   └── utils/
│       └── convert_model.sh # Main conversion script
├── tests/
│   ├── chat.py              # Chat interface
│   └── chat_full.py         # Full conversation mode
├── models/                  # Output directory for converted models
└── SETUP_NOTES.md           # This file
```

---

## Quick Start (After macOS Upgrade)

```bash
# 1. Navigate to project
cd /Users/agundez/Build/Anemll

# 2. Activate environment
source env-anemll/bin/activate

# 3. Test pre-downloaded model
python ./tests/chat.py --meta ~/.cache/huggingface/hub/models--anemll--anemll-Qwen-Qwen2.5-0.5B-Instruct-ctx2048-monolithic_0.3.5/snapshots/4a2af987aca06f20663be1ce550a85f72aa72f03/meta.yaml

# 4. Start chatting!
```

---

---

## macOS 15.1 Installer Archive

**Why 15.1?** User reports indicate 15.1 was more stable than 15.2+ (battery drain, bugs introduced later).

### Download Sources (Direct from Apple CDN)

| File | Build | Purpose |
|------|-------|---------|
| `InstallAssistant.pkg` | 24B83 | Upgrade from Sonoma with data retention |
| `UniversalMac_15.1_24B83_Restore.ipsw` | 24B83 | DFU restore, VMs, clean install |

### Download Methods

**Apple CDN (15.1 NO LONGER AVAILABLE)**
```bash
# This no longer works - Apple removed 15.1 from their servers
softwareupdate --fetch-full-installer --full-installer-version 15.1  # Returns 403
```

**Internet Archive (WORKING - Oct 2024)**
```bash
# 15.1 preserved on archive.org
curl -L -o ~/Downloads/InstallAssistant-15.1-24B83.pkg \
  "https://archive.org/download/macOS-24B83-InstallAssistant/InstallAssistant.pkg"
```

Source: [Internet Archive - macOS 15.1 (24B83)](https://archive.org/details/macOS-24B83-InstallAssistant)

**Verification (SHA1):** `dd9de210d96e0558bebd62562d4067e3d1731c41`

### Create Bootable USB
```bash
# Install the pkg first
sudo installer -pkg ~/Downloads/InstallAssistant.pkg -target /

# Create bootable USB
sudo /Applications/Install\ macOS\ Sequoia.app/Contents/Resources/createinstallmedia \
  --volume /Volumes/USBDrive
```

### Archive Location
```
~/Downloads/InstallAssistant-15.1-24B83.pkg  (14 GB, verified)
```

**Status:** ✅ Downloaded and verified (SHA1 matches)

**Note:** Apple has already removed 15.1 from their CDN (403 Forbidden). This copy was retrieved from Internet Archive on 2024-10-24.

---

## References

- ANEMLL GitHub: https://github.com/Anemll/Anemll
- Pre-converted Models: https://huggingface.co/anemll
- macOS Sequoia: https://www.apple.com/macos/macos-sequoia/
- macOS 15.1 Installer: https://mrmacintosh.com/macos-sequoia-full-installer-database-download-directly-from-apple/
