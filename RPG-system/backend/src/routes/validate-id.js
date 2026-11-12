export function validateIdParam(router) {
  router.param('id', (req, res, next, value) => {
    const id = Number(value);
    if (!Number.isInteger(id) || id < 1) return res.status(400).json({ error: 'ID inválido.' });
    req.params.id = id;
    next();
  });
  return router;
}
