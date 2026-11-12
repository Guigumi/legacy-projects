export function requireAuth(req, res, next) {
  if (req.session && req.session.autenticado === true) {
    return next();
  }
  return res.status(401).json({ error: 'Não autenticado.' });
}
