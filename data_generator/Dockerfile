# Crestmount Refinery — data generator + agent workshop runtime
FROM python:3.11-slim

WORKDIR /app

# System deps for numpy/pandas
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first for layer caching
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    "numpy>=1.26" "pandas>=2.2" "pyyaml>=6.0" "pytest>=8.0" \
    streamlit plotly

# Copy the project
COPY . .

# Default: generate data, build the DB, and run the agent pipeline
RUN mkdir -p /app/output
CMD ["sh", "-c", "python generate_data.py --seed 42 --output-dir ./output && python run_agents.py --db ./output/crestmount.db --build-db --output-dir ./output"]
