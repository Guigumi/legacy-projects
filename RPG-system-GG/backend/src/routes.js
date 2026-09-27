import { Router } from 'express';
import systemRouter from './routes/system.js';
import compendiumRouter from './routes/compendium.js';
import charactersRouter from './routes/characters.js';
import bestiaryRouter from './routes/bestiary.js';
import combatsRouter from './routes/combats.js';
import effectsRouter from './routes/effects.js';
import importsRouter from './routes/imports.js';
import roteirosRouter from './routes/roteiros.js';
import transmissionRouter from './routes/transmission.js';

const router = Router();

router.use(systemRouter);
router.use(compendiumRouter);
router.use(charactersRouter);
router.use(bestiaryRouter);
router.use(combatsRouter);
router.use(effectsRouter);
router.use(importsRouter);
router.use(roteirosRouter);
router.use(transmissionRouter);

export default router;
