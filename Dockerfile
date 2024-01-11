# Use an official Python runtime as a parent image
FROM python:3.8-slim

# Set the working directory in the container
WORKDIR /usr/src/app

# Copy the current directory contents into the container at /usr/src/app
COPY . .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir boto3 argparse

# Run aws_cleanup.py when the container launches, entrypoint can be overridden
ENTRYPOINT ["python", "./aws_cleanup.py"]
