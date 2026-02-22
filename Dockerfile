# Use an official Python runtime as a parent image
FROM python:3.11-slim-bookworm

# Set the working directory in the container
WORKDIR /app

# Copy the consolidated requirements file and install dependencies
COPY requirements.docker.txt .
RUN pip install --no-cache-dir -r requirements.docker.txt

# Copy pyproject.toml for editable install (if needed)
COPY pyproject.toml .

# Copy the rest of the application code
COPY . .

# Install the project in editable mode
# This makes the 'agos' package available
RUN pip install -e .

# Define environment variable for Python path
ENV PYTHONPATH=/app

# Default command - this will be overridden by docker-compose for specific services
# This is just a placeholder to keep the container running if nothing else is specified.
# A simple sleep or a shell entrypoint might be better if no specific default action.
# For now, let's make it print python version, which is harmless.
CMD ["python", "--version"]
