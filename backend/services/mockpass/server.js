#!/usr/bin/env node
/**
 * MockPass with MyInfo v3 test endpoint.
 * Runs MockPass via CLI and adds a proxy server for the test endpoint.
 */

const fs = require('fs');
const path = require('path');
const express = require('express');
const { spawn } = require('child_process');
const http = require('http');

// Prefer the repo-managed v3.json so demo scenarios stay in sync with runtime.
const myinfoV3Path = process.env.MYINFO_V3_PATH || path.join(__dirname, 'v3.json');

let myinfoData = {};
try {
  myinfoData = JSON.parse(fs.readFileSync(myinfoV3Path, 'utf-8'));
  console.log(`Loaded MyInfo v3 test data from ${myinfoV3Path}`);
} catch (error) {
  console.error('Failed to load MyInfo v3 data:', error.message);
  process.exit(1);
}

const port = process.env.PORT || process.env.MOCKPASS_PORT || 5156;

const app = express();
app.use(express.json());

function withDerivedMonthlyIncome(personaData) {
  if (!personaData || typeof personaData !== 'object') {
    return personaData;
  }

  if (personaData.monthlyincome?.value !== undefined) {
    return personaData;
  }

  const annualIncome =
    personaData.noa?.amount?.value ??
    personaData.noa?.employment?.value;

  if (typeof annualIncome !== 'number') {
    return personaData;
  }

  return {
    ...personaData,
    monthlyincome: {
      value: Number((annualIncome / 12).toFixed(2)),
    },
  };
}

app.get('/myinfo/v3/test-person', (req, res) => {
  const uinfin = String(req.query.uinfin || '').toUpperCase().trim();

  if (!uinfin) {
    return res.status(400).json({
      error: 'uinfin parameter required',
      example: '/myinfo/v3/test-person?uinfin=S9812381D',
    });
  }

  const personaData = myinfoData.personas?.[uinfin];
  if (!personaData) {
    return res.status(404).json({
      error: 'Profile not found',
      message: `No test data available for ${uinfin}`,
    });
  }

  return res.json({
    uinfin: { value: uinfin },
    ...withDerivedMonthlyIncome(personaData),
  });
});

// Proxy all other requests to MockPass running on port 5157 internally.
app.use((req, res) => {
  const options = {
    hostname: 'localhost',
    port: 5157,
    path: req.originalUrl,
    method: req.method,
    headers: req.headers,
  };

  const proxyReq = http.request(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res);
  });

  proxyReq.on('error', (error) => {
    console.error('MockPass proxy error:', error.message);
    res.status(503).json({ error: 'MockPass unavailable' });
  });

  if (req.method !== 'GET' && req.method !== 'HEAD') {
    req.pipe(proxyReq);
  } else {
    proxyReq.end();
  }
});

app.listen(port, '0.0.0.0', () => {
  console.log(`Test endpoint proxy listening on ${port}`);
  console.log('GET /myinfo/v3/test-person?uinfin=S9812381D\n');

  console.log('Starting MockPass on port 5157...');
  const mockpass = spawn('npx', ['mockpass', '--port', '5157'], {
    env: {
      ...process.env,
      MOCKPASS_PORT: '5157',
      PORT: '5157',
    },
    stdio: 'inherit',
  });

  mockpass.on('error', (error) => {
    console.error('MockPass failed:', error);
    process.exit(1);
  });

  mockpass.on('exit', (code) => {
    console.log('MockPass exited with code', code);
    process.exit(code);
  });

  process.on('SIGTERM', () => {
    console.log('Shutting down...');
    mockpass.kill();
    process.exit(0);
  });
});
