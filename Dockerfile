FROM mcr.microsoft.com/playwright/python:v1.44.0-noble

WORKDIR /app

# Copy requirement list and script
COPY code.py /app/code.py

# Install additional python packages
RUN pip install --no-cache-dir tqdm

# Command to execute script continuously
CMD ["python", "-u", "code.py"]
