# Quick Start Guide for Normalization Worker

## 1. Local Development Setup

### Prerequisites
- Python 3.11+
- RabbitMQ (local or Docker)
- Access to OXP Backend for data lake

### Installation

```bash
cd norm-worker

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e .
```

## 2. Running RabbitMQ Locally

```bash
# Access management UI at http://localhost:15672
# Default credentials: guest/guest
```

## 3. Running the Worker

### Basic Mode

```bash
norm-worker-cli
```

This will:
- Connect to RabbitMQ at `amqp://guest:guest@localhost:5672/`
- Listen on queue `new_session_in`
- Forward processed sessions to `new_session_to_mce` and `new_session_to_embedding`

### With Custom Configuration

```bash
norm-worker-cli \
  --input-queue my_queue \
  --output-queue downstream_queue \
  --max-sessions 10 \
  --debug
```

### Debug Mode

```bash
norm-worker-cli --debug
```

Outputs:
- Detailed logs to console
- Raw session data: `/tmp/dal_session_*.json`
- Normalized data: `/tmp/norm_session.json`
- Transition diagrams: `/tmp/norm_transitions.html`

## 4. Sending Test Messages

### Using Python

```python
import asyncio
import aio_pika
import json

async def send_test_message():
    connection = await aio_pika.connect_robust("amqp://guest:guest@localhost/")
    channel = await connection.channel()
    
    message_body = {
        "session_id": "test_session_12345",
        "job_id": "job_001",
        "workflow_id": "wf_001"
    }
    
    message = aio_pika.Message(
        body=json.dumps(message_body).encode(),
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )
    
    await channel.default_exchange.publish(
        message,
        routing_key="new_session_in"
    )
    
    await connection.close()
    print("Message sent!")

asyncio.run(send_test_message())
```

### Using RabbitMQ Management UI

1. Go to http://localhost:15672
2. Login with guest/guest
3. Go to Queues tab
4. Find `new_session_in` queue
5. Click "Publish message"
6. Paste JSON message:
```json
{
  "session_id": "test_session_12345",
  "job_id": "job_001",
  "workflow_id": "wf_001"
}
```

## 5. Monitoring

### View Queue Status

```bash
# Using RabbitMQ management UI
# http://localhost:15672 -> Queues tab

# Or check logs from worker
# Look for "Processing session_id" messages
```

### View Processed Data

```bash
# In debug mode, check temp files
ls -la /tmp/dal_session_*.json
ls -la /tmp/norm_session.json
cat /tmp/norm_transitions.html

# Or check RabbitMQ output queues
```

## 6. Run-once Integration (Argo Workflows Compatible)

### Single Message Processing

```bash
# Create input file
cat > input.json <<EOF
{
  "session_id": "session_001",
  "job_id": "job_001",
  "workflow_id": "wf_001"
}
EOF

# Process with worker
norm-worker-cli \
  --run-once \
  --input input.json \
  --output output.json \
  --debug

# Check output
cat output.json
```

## 8. Troubleshooting

### Worker not starting

```bash
# Check network connectivity
python -c "import aio_pika; print('OK')"

# Check environment variables
echo $RABBITMQ_URL
```

### Sessions not processing

1. Check input queue has messages (RabbitMQ UI)
2. Ensure DAL/data lake is accessible
4. Try with `--debug` flag for detailed output

### Memory issues

- Reduce number of parallel workers
- Use `--max-sessions` to limit processing
- Monitor RabbitMQ prefetch count

## 9. Common Commands

```bash
# Run and test immediately
norm-worker-cli --test

# Process 5 sessions then stop
norm-worker-cli --max-sessions 5

# Run with specific RabbitMQ
norm-worker-cli --rabbitmq-url amqp://user:pass@rabbitmq.example.com/

# Debug normalization
norm-worker-cli --debug --max-sessions 1

# No output queues (testing only)
norm-worker-cli --output-queue ""
```

## 10. Next Steps

- Check [README.md](README.md) for full documentation
- Review source code in `src/norm_worker/`
- Add custom metrics in the worker
- Integrate with CI/CD pipeline
- Scale to multiple worker instances
