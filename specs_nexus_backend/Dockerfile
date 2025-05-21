 FROM python:3.9-slim

 # Set environment variables
 ENV PYTHONDONTWRITEBYTECODE=1
 ENV PYTHONUNBUFFERED=1
 ENV PYTHONPATH=/app

 # Set working directory
 WORKDIR /app

 # Copy requirements.txt and install dependencies
 COPY requirements.txt .
 RUN pip install --no-cache-dir -r requirements.txt

 # Install system dependencies for faiss-cpu
 RUN apt-get update && apt-get install -y \
     libopenblas-dev \
     libomp-dev \
     && rm -rf /var/lib/apt/lists/*

 # Copy the entire project
 COPY . .

 # Generate FAISS index
 RUN python build_index.py

 # Make prestart.sh executable
 COPY prestart.sh .
 RUN chmod +x prestart.sh

 # Expose port 8000
 EXPOSE 8000

 # Run prestart.sh and start the FastAPI app
 CMD ["sh", "-c", "./prestart.sh && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
