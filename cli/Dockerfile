# Use Python 3.11 slim image for smaller size
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml first for better caching
COPY pyproject.toml ./

# Install the CLI package in development mode
RUN pip install --no-cache-dir -e .

# Copy the rest of the CLI code
COPY . .

# Set environment variables
ENV PYTHONPATH=/app

# Create a volume for reports
VOLUME ["/app/reports"]

# Default command shows help  
CMD ["python", "cli.py", "help"]
