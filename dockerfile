# Base Image
FROM python:3.9
WORKDIR /app

# Install system dependencies (needed for some math libraries)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the project files
COPY . .

# Expose the Jupyter port
EXPOSE 8888

# Command to launch Jupyter Lab
# --ip=0.0.0.0 allows access from outside the container
# --allow-root is needed because Docker runs as root
# --NotebookApp.token='' removes the password (Convenient for judges)
CMD ["jupyter", "lab", "--ip=0.0.0.0", "--port=8888", "--no-browser", "--allow-root", "--NotebookApp.token=''"]