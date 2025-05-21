# Use the official Python 3.9 slim image
   FROM python:3.9-slim

   # Set environment variables to prevent Python from writing .pyc files and buffering stdout/stderr
   ENV PYTHONDONTWRITEBYTECODE=1
   ENV PYTHONUNBUFFERED=1
   ENV PYTHONPATH=/app

   # Set working directory
   WORKDIR /app

   # Copy requirements.txt and install dependencies
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt

   # Install additional system dependencies for faiss and other libraries
   RUN apt-get update && apt-get install -y \
       libopenblas-dev \
       libomp-dev \
       && rm -rf /var/lib/apt/lists/*

   # Copy the entire project
   COPY . .

   # Expose port 8000
   EXPOSE 8000

   # Run the FastAPI app with Uvicorn
   CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]