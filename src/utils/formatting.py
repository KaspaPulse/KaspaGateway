def format_large_number(num: float, precision: int = 2) -> str:
    if not isinstance(num, (int, float)) or num < 0:
        return "N/A"
    if num == 0:
        return f"0.{'0' * precision}"
    
    power = 1000.0
    n = 0
    power_labels = {0: '', 1: 'K', 2: 'M', 3: 'B', 4: 'T', 5: 'P'}
    
    while num >= power and n < len(power_labels) - 1:
        num /= power
        n += 1
    
    return f"{num:,.{precision}f}{power_labels[n]}"

def format_hashrate(ths: float, precision: int = 2) -> str:
    if not isinstance(ths, (int, float)) or ths < 0:
        return "N/A"
    if ths == 0:
        return f"0.{'0' * precision} TH/s"
    
    if ths >= 1_000_000:
        return f"{ths / 1_000_000:,.{precision}f} EH/s"
    if ths >= 1_000:
        return f"{ths / 1_000:,.{precision}f} PH/s"
    return f"{ths:,.{precision}f} TH/s"









def mask_address(address: str, prefix=8, suffix=5) -> str:
    if not address or not isinstance(address, str):
        return "N/A"
    try:
        if "kaspa:" in address:
            parts = address.split(':')
            prefix_part = parts[0]
            addr_part = parts[1]
            if len(addr_part) > prefix + suffix:
                return f"{prefix_part}:{addr_part[:prefix]}...{addr_part[-suffix:]}"
        if len(address) > prefix + suffix:
            return f"{address[:prefix]}...{address[-suffix:]}"
    except Exception:
        pass
    return address