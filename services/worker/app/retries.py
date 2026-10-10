import time

def retry(operation, attempts:int=3, base_delay:float=0.5):
    last=None
    for attempt in range(max(1,attempts)):
        try: return operation()
        except Exception as exc:
            last=exc
            if attempt+1 < attempts: time.sleep(base_delay*(2**attempt))
    raise last
