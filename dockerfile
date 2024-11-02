# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install Poetry
RUN pip install poetry

# Configure Poetry:
# - Disable virtual env creation: It's unnecessary inside Docker
# - Don't ask any interactive question
RUN poetry config virtualenvs.create false \
    && poetry config --list

# Install dependencies using Poetry
RUN poetry install --no-dev --no-interaction --no-ansi

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Define environment variable for the Flask app
ENV NAME World
ENV FLASK_APP app.py  # This should be the name of your main Flask script
ENV FLASK_ENV development  # Optional: Only for development; remove in production

# Run the application
CMD ["poetry", "run", "flask", "run", "--host=0.0.0.0"]
