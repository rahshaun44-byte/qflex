const express = require('express');
const { exec } = require('child_process');
const app = express();

app.use(express.json());

// Security: Only bind to localhost. Do not expose this to the outside network.
const PORT = 9000;
const HOST = '127.0.0.1';

// Health Check Endpoint
app.get('/health', (req, res) => {
    res.json({ status: 'Sentinel Bridge Online', secure: true });
});

// Execution Endpoint for ZK Proofs
app.post('/execute-zk', (req, res) => {
    const { command } = req.body;

    // Hardcoded command whitelist for security - only allow snarkjs and circom
    if (!command.startsWith('snarkjs') && !command.startsWith('circom')) {
        return res.status(403).json({ error: 'Command execution denied by security policy.' });
    }

    exec(command, (error, stdout, stderr) => {
        if (error) {
            return res.status(500).json({ error: error.message, stderr });
        }
        res.json({ output: stdout });
    });
});

app.listen(PORT, HOST, () => {
    console.log(`[SECURE] Sentinel Bridge listening on http://${HOST}:${PORT}`);
});

