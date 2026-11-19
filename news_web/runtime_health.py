def restart_needed(healthy, running, failures, uptime, ever_ready):
    if healthy:
        return False
    if not running:
        return True
    if not ever_ready and uptime < 180:
        return False
    return failures >= 3
