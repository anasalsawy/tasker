"""Start Tasker's local API without Python 3.14's blocking WMI probe."""
import sys
import platform
import os

if sys.platform == "win32":
    platform.system = lambda: "Windows"
    platform.machine = lambda: "AMD64"

# Avoid a Python 3.14 Windows certificate-store enumeration that can block
# during LangChain/OpenAI imports on some machines.
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except ImportError:
    pass

import uvicorn


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000)
