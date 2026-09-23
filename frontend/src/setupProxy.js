const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function(app) {
  app.use(
    '/api',
    createProxyMiddleware({
      target: 'http://localhost:5001',
      changeOrigin: true,
      timeout: 30000,
      onError: (err, req, res) => {
        console.log('Proxy error:', err.message);
        res.writeHead(500, {
          'Content-Type': 'text/plain',
        });
        res.end('Proxy error: ' + err.message);
      },
      onProxyReq: (proxyReq, req, res) => {
        console.log('Proxying request:', req.method, req.url);
      }
    })
  );
  
  app.use(
    '/manifest.json',
    createProxyMiddleware({
      target: 'http://localhost:5001',
      changeOrigin: true,
      timeout: 30000,
    })
  );
  
  app.use(
    '/favicon.ico',
    createProxyMiddleware({
      target: 'http://localhost:5001',
      changeOrigin: true,
      timeout: 30000,
    })
  );
};
