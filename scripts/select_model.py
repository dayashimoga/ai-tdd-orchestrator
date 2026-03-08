import os
import subprocess
import platform

def get_total_memory_gb():
    """Gets total system RAM in GB safely cross-platform."""
    try:
        # Linux
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if 'MemTotal' in line:
                    return int(line.split()[1]) / 1024 / 1024
    except Exception:
        pass
    
    try:
        # macOS / BSD
        out = subprocess.check_output(['sysctl', '-n', 'hw.memsize']).decode('utf-8')
        return int(out) / 1024 / 1024 / 1024
    except Exception:
        pass

    try:
        # Windows (E4: wmic fallback)
        if platform.system() == "Windows":
            out = subprocess.check_output(
                ['wmic', 'ComputerSystem', 'get', 'TotalPhysicalMemory', '/value'],
                stderr=subprocess.DEVNULL
            ).decode('utf-8')
            for line in out.strip().split('\n'):
                if 'TotalPhysicalMemory' in line:
                    val = line.split('=')[1].strip()
                    return int(val) / 1024 / 1024 / 1024
    except Exception:
        pass
        
    # Assume minimal Free Tier limit if we can't detect
    return 6.0 

def get_gpu_vram_gb():
    """Gets total Nvidia GPU VRAM in GB if available."""
    try:
        out = subprocess.check_output(
            ['nvidia-smi', '--query-gpu=memory.total', '--format=csv,noheader,nounits'], 
            stderr=subprocess.DEVNULL
        ).decode('utf-8')
        # Sum VRAM if multiple GPUs just as an estimate envelope
        vram_mb = sum(int(x) for x in out.strip().split('\n'))
        return vram_mb / 1024
    except Exception:
        return 0.0

def select_optimal_model():
    """Selects the best coder model based on hardware limits."""
    ram_gb = get_total_memory_gb()
    vram_gb = get_gpu_vram_gb()
    

    # Rule 1: High VRAM (DeepSeek-Coder 33B or Qwen 32B)
    if vram_gb >= 24.0:
        return "qwen2.5-coder:32b"
    
    # Rule 2: Mid-tier Local (7B-10B class) - Local Docker / Workstations
    if ram_gb >= 15.0:
        return "qwen2.5-coder:7b"
        
    # Rule 3: GitHub Free Runner (7GB RAM, 0 VRAM) - The 3B Model Fallback
    return "qwen2.5-coder:3b"

def main():
    ram = get_total_memory_gb()
    vram = get_gpu_vram_gb()
    model = select_optimal_model()
    
    print("\n==============================================")
    print("🧠 AI REVIEWER INTELLIGENCE - HARDWARE SCAN")
    print("==============================================")
    print(f"🖥️ System OS:       {platform.system()} {platform.release()}")
    print(f"🧠 Total RAM:       {ram:.2f} GB")
    print(f"🎮 Dedicated VRAM:  {vram:.2f} GB")
    print(f"⚙️ Selected Model:  {model}")
    print("==============================================\n")
    
    github_env = os.getenv("GITHUB_ENV")
    if github_env:
        with open(github_env, "a") as f:
            f.write(f"SELECTED_MODEL={model}\n")
        
        step_summary = os.getenv("GITHUB_STEP_SUMMARY")
        if step_summary:
            with open(step_summary, "a") as f:
                f.write(f"### 🧠 AI Model Selected: `{model}`\n")
                f.write(f"- **System OS:** {platform.system()} {platform.release()}\n")
                f.write(f"- **System RAM:** {ram:.2f} GB\n")
                f.write(f"- **System VRAM:** {vram:.2f} GB\n")
    
    print(model)

if __name__ == "__main__":
    main()
