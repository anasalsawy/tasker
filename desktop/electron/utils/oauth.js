import crypto from 'crypto';

function base64URLEncode(str) {
  return str.toString('base64')
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

function sha256(buffer) {
  return crypto.createHash('sha256').update(buffer).digest();
}

export function generatePKCE() {
  const codeVerifier = base64URLEncode(crypto.randomBytes(32));
  const codeChallenge = base64URLEncode(sha256(Buffer.from(codeVerifier)));
  return { codeVerifier, codeChallenge };
}
