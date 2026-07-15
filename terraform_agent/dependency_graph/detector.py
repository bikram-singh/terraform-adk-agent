import re

def detect_architecture_type(request: str) -> str:
    value = re.sub(r"\s+", " ", request.strip().lower())
    cloud_run = "cloud run" in value or "cloud-run" in value
    cloud_sql = any(x in value for x in ("cloud sql", "cloud-sql", "postgres", "mysql"))
    private = any(x in value for x in ("private", "no public ip", "internal"))
    if cloud_run and cloud_sql and private:
        return "private-cloud-run-cloud-sql"
    return "unsupported"
