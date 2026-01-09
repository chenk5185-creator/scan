FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Railway uses PORT env variable
ENV PORT=8501

# Run streamlit with dynamic port
CMD streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true
