/* Foreground-only collection controller. No attack, shop, repair or respawn commands. */
(() => {
  if (window.AutoBoxAndroid) return;
  const finite = v => typeof v === 'number' && Number.isFinite(v);
  let running = false, mode = 'ship', context = null, target = null;
  let lastServerTime = null, lastFreshAt = 0, observedAdvance = false;
  let best = Infinity, progressAt = 0, nextAction = 0, confirmed = 0, baseline = null;
  let deferred = new Map(), patrol = null, patrolIndex = 0, petPendingAt = null;
  const key = b => String(b.id) + ':' + b.revision;
  function cancel() {
    window.DarkOrbitGroups?.onFollowCancel?.();
  }
  function stop(message = 'Coleta pausada.') {
    running = false; target = null; patrol = null;
    try { cancel(); } catch (_) { /* No retries from a paused controller. */ }
    return { running: false, status: message, confirmed };
  }
  function start(value) {
    if (!['ship','pet'].includes(value)) return stop('Modo de coleta inválido.');
    stop(); mode = value; context = null; target = null;
    lastServerTime = null; lastFreshAt = Date.now(); observedAdvance = false;
    nextAction = 0; deferred = new Map(); patrol = null; petPendingAt = null;
    running = true;
    return { running: true, status: 'Aguardando dados atuais do mapa…', confirmed };
  }
  function tick() {
    if (!running) return { running: false, status: 'Coleta pausada.', confirmed };
    const now = Date.now(), W = window.PeriodWindows, r = W?.renderer;
    const s = r?.state, me = s?.me, G = window.DarkOrbitGroups;
    if (!s || !me || !r || W.readOnly) return stop('Entre no mapa do jogo antes de iniciar.');
    if (typeof G?.onFollow !== 'function' || typeof G?.onFollowCancel !== 'function')
      return stop('Controle do cliente indisponível nesta versão do jogo.');
    if (![me.x,me.y,me.hp,me.maxHp,s.time].every(finite) || me.maxHp <= 0)
      return stop('Posição, vida ou relógio do jogo indisponível.');
    if (lastServerTime !== null && s.time < lastServerTime) return stop('Relógio do jogo mudou; inicie novamente.');
    if (lastServerTime === null || s.time !== lastServerTime) {
      if (lastServerTime !== null) observedAdvance = true;
      lastServerTime = s.time; lastFreshAt = now;
    }
    if (now-lastFreshAt > 6000) return stop('Dados parados ou conexão perdida. Inicie após reconectar.');
    if (!observedAdvance) return { running: true, status: 'Confirmando atualização do mapa…', confirmed };
    if (!['string','number'].includes(typeof me.id) || typeof me.mapId !== 'string' || !Number.isInteger(me.respawnRevision))
      return stop('Identificação da nave indisponível.');
    if (me.hp <= 0 || me.deadUntil) return stop('Nave destruída. Recupere no jogo.');
    if (me.hp / me.maxHp <= .25) return stop('Vida em 25% ou menos. Recupere no jogo.');
    if (me.attacking || me.secondaryVolley || me.pendingJump) return stop('Combate ou salto ativo. Coleta pausada.');
    if (G.isPingArmed?.()) return stop('Desative a marcação de grupo antes de coletar.');
    const width = s.map?.width ?? s.world?.width, height = s.map?.height ?? s.world?.height;
    if (![width,height].every(finite) || width <= 320 || height <= 320) return stop('Limites do mapa indisponíveis.');
    const current = JSON.stringify([me.id,me.mapId,me.respawnRevision,me.activeConfiguration]);
    if (context !== null && context !== current) return stop('Conta, mapa, vida ou configuração mudou. Inicie novamente.');
    context = current;
    const info = { running: true, confirmed, map: me.mapId,
      hp: Math.round(100*me.hp/me.maxHp), uridium: finite(me.uridium) ? me.uridium : null };
    if (mode === 'pet') {
      try {
        if (petPendingAt !== null) {
          const inspected = window.AutoBoxAndroidPet({action:'inspect'});
          if (now-petPendingAt.started > 20000) return stop('PET sem confirmação. Confira equipamento e combustível.');
          const activeOk = petPendingAt.active === undefined || inspected.active === petPendingAt.active;
          const modeOk = petPendingAt.mode === undefined || inspected.mode === petPendingAt.mode;
          if (activeOk && modeOk) { petPendingAt = null; nextAction = 0; }
          else return {...info,status:'PET: aguardando confirmação…'};
        }
        if (now < nextAction && !target) return {...info,status:'Aguardando disponibilidade do PET…'};
        const result = window.AutoBoxAndroidPet({ action: 'ensure' });
        if (result.action !== 'ready') {
          if (result.action === 'sent') petPendingAt = {started:now,active:result.expected_active,mode:result.expected_mode};
          nextAction = now+1000;
          return { ...info, status: 'Preparando PET; aguardando confirmação…' };
        }
      } catch (e) { return stop(String(e.message || e)); }
    }
    for (const [id,until] of deferred) if (until <= now) deferred.delete(id);
    const boxes = (Array.isArray(s.boxes) ? s.boxes : []).filter(b =>
      ['box','bonus',undefined,null].includes(b.kind) &&
      typeof b.id === 'string' && Number.isInteger(b.revision) &&
      [b.x,b.y].every(finite) && b.x >= 80 && b.y >= 80 && b.x <= width-80 && b.y <= height-80);
    const counter = me.achievements?.counters?.bonusboxes;
    if (target && !boxes.some(b => key(b) === key(target))) {
      if (mode === 'ship' && finite(counter) && finite(baseline) && counter > baseline && best <= 180) confirmed++;
      target = null; nextAction = 0; best = Infinity;
    }
    if (!target) {
      const candidates = boxes.filter(b => !deferred.has(key(b)));
      candidates.sort((a,b) => Math.hypot(a.x-me.x,a.y-me.y)-Math.hypot(b.x-me.x,b.y-me.y));
      if (candidates.length) {
        target = { ...candidates[0] }; best = Infinity; progressAt = now; baseline = counter; nextAction = 0; patrol = null;
      }
    }
    if (target) {
      const live = boxes.find(b => key(b) === key(target));
      if (!live) return { ...info, confirmed, status: 'Reavaliando boxes…' };
      const d = Math.hypot(live.x-me.x,live.y-me.y);
      if (d < best-5) { best = d; progressAt = now; }
      if (mode === 'pet' && target.destination && best <= 180 && d > 600) {
        deferred.set(key(target),now+10000);target=null;nextAction=0;
        return {...info,status:'Box atravessada; procurando a próxima para o PET…'};
      }
      if (now-progressAt >= 8000) { deferred.set(key(target),now+30000); target = null; nextAction = 0; }
      else if (now >= nextAction) {
        try {
          if (mode === 'pet') {
            if (!target.destination) {
              const result=window.AutoBoxAndroidPet({ action: 'move', id: live.id, revision: live.revision, x: live.x, y: live.y });
              if (result.action==='move') target.destination=result.destination;
              else if (['blocked','passed','gone'].includes(result.action)) {deferred.set(key(target),now+10000);target=null;}
              else throw Error('Resposta de movimento PET desconhecida.');
            } else window.AutoBoxAndroidPet({action:'cruise',...target.destination});
            nextAction = now+900;
          } else {
            const result = window.AutoBoxAndroidTarget({ ...live, map: me.mapId, allow_green: false, can_collect: true, can_move: false });
            if (result.action === 'collect') nextAction = now+3000;
            else { G.onFollow({x:live.x,y:live.y,mapId:me.mapId}); nextAction = now+1200; }
          }
        } catch (e) { return stop(String(e.message || e)); }
      }
      return { ...info, confirmed, boxes: boxes.length,
        status: target ? (mode === 'pet' ? 'PET coletando · ' : 'Coletando · ') + Math.round(d) + ' unidades da box' : 'Box sem progresso; procurando outra.' };
    }
    if (!patrol || Math.hypot(patrol.x-me.x,patrol.y-me.y) < 250) {
      const points = [[.25,.25],[.75,.25],[.75,.75],[.25,.75]];
      const p = points[patrolIndex++ % points.length]; patrol = { x:width*p[0],y:height*p[1] }; nextAction = 0;
    }
    if (now >= nextAction) {
      if (mode === 'pet') {
        try { window.AutoBoxAndroidPet({action:'cruise',...patrol}); }
        catch (e) { return stop(String(e.message || e)); }
      } else G.onFollow({...patrol,mapId:me.mapId});
      nextAction = now+1500;
    }
    return {...info,confirmed,boxes:boxes.length,status:'Procurando boxes no interior do mapa…'};
  }
  window.AutoBoxAndroid = { start, tick, stop };
})();
