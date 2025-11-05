/** @type {import('next').NextConfig} */
module.exports = {
  // allow dev traffic from these hostnames in addition to the server’s own host
  // Hosts only; omit scheme and port (Next docs recommend hostnames only).
  allowedDevOrigins: ['127.0.0.1', 'localhost'],
};
