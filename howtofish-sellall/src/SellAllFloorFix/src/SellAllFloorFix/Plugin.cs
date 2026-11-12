using System.Collections;
using System.Collections.Generic;
using BepInEx;
using BepInEx.Logging;
using UnityEngine;

namespace SellAllFloorFix
{
    [BepInPlugin("Guigumi.SellAllFloorFix", "SellAllFloorFix", "1.2.0")]
    public sealed class Plugin : BaseUnityPlugin
    {
        internal static ManualLogSource Log = null!;
        internal SellAllConfig Cfg = null!;
        private float _lastRun = -999f;
        private bool _running;
        private string _hudMessage = "";
        private string _hudWarning = "";
        private string _lastBlockedFeedback = "";
        private float _hudMessageUntil;
        private float _nextBlockedFeedbackAt = -999f;
        private GUIStyle? _hudStyle;
        private GUIStyle? _hudWarningStyle;

        private void Awake()
        {
            Log = Logger;
            Cfg = new SellAllConfig(Config);
            Log.LogInfo("SellAllFloorFix v1.2.0 loaded. Tecla: " + Cfg.Tecla.Value);
        }

        private void OnDisable() { _running = false; }
        private void OnDestroy() { _running = false; }

        private void Update()
        {
            if (!Cfg.Tecla.Value.IsDown()) return;

            if (_running)
            {
                ShowBlockedFeedback("Venda em andamento", "running");
                return;
            }

            if (!Despawner.IsServer())
            {
                if (ShowBlockedFeedback("Só o host pode vender", "host"))
                    Log.LogInfo("SellAll: apenas o host pode vender. Peça ao host para apertar " + Cfg.Tecla.Value + ".");
                return;
            }

            float cooldownRemaining = Cfg.CooldownSeg.Value - (Time.realtimeSinceStartup - _lastRun);
            if (cooldownRemaining > 0f)
            {
                float roundedRemaining = Mathf.Ceil(cooldownRemaining * 10f) / 10f;
                string seconds = roundedRemaining.ToString("0.0", System.Globalization.CultureInfo.InvariantCulture);
                ShowBlockedFeedback("Aguarde " + seconds + " s", "cooldown");
                return;
            }

            _lastRun = Time.realtimeSinceStartup;
            ShowStatus("Iniciando venda…", 1.25f);
            TrySellAll();
        }

        private void TrySellAll()
        {
            int paidButPending = 0;
            try
            {
                _running = true;
                var items = ItemCollector.Collect();
                bool cleanNoValue = !Cfg.SoVendaveis.Value || Cfg.IncluirSemValor.Value;
                var fallbackItems = new List<GroundItem>();
                var paidItems = new List<GroundItem>();
                var cleanupItems = new List<GroundItem>();
                var warnings = new List<string>();
                long fallbackTotalLong = 0;
                long nativeTotal = 0;
                int unknownWorth = 0;
                int noNetworkRoute = 0;
                int uncertainCredit = 0;

                foreach (var item in items)
                {
                    if (!item.WorthKnown)
                    {
                        unknownWorth++;
                        Log.LogWarning("SellAll: valor não reconhecido para '" + item.Name + "'; item mantido.");
                        continue;
                    }

                    if (item.Worth <= 0)
                    {
                        if (!cleanNoValue) continue;
                        if (!Despawner.CanDespawnNetwork(item, out string cleanReason))
                        {
                            noNetworkRoute++;
                            Log.LogWarning("SellAll: '" + item.Name + "' não pode ser limpo: " + cleanReason + ".");
                            continue;
                        }
                        cleanupItems.Add(item);
                        continue;
                    }

                    // Confere a rota de rede antes de creditar para não pagar item que já
                    // sabemos que não conseguiremos remover do servidor.
                    if (!Despawner.CanDespawnNetwork(item, out string sellReason))
                    {
                        noNetworkRoute++;
                        Log.LogWarning("SellAll: '" + item.Name + "' mantido sem venda: " + sellReason + ".");
                        continue;
                    }

                    var nativeResult = Seller.TryNativeSell(item.Component);
                    if (nativeResult == TransactionAttemptResult.Confirmed)
                    {
                        paidItems.Add(item);
                        paidButPending++;
                        nativeTotal += item.Worth;
                    }
                    else if (nativeResult == TransactionAttemptResult.Unavailable)
                    {
                        fallbackItems.Add(item);
                        fallbackTotalLong += item.Worth;
                    }
                    else
                    {
                        uncertainCredit++;
                        Log.LogWarning("SellAll: crédito possivelmente aplicado para '" + item.Name + "'; fallback e despawn cancelados.");
                    }
                }

                long fallbackTotal = 0;
                if (fallbackItems.Count > 0)
                {
                    if (fallbackTotalLong > int.MaxValue)
                    {
                        warnings.Add("Crédito excede o limite suportado; " + fallbackItems.Count + " item(ns) mantido(s).");
                        Log.LogWarning("SellAll: total fallback excede Int32; itens mantidos no chão.");
                    }
                    else
                    {
                        var creditResult = Seller.Credit((int)fallbackTotalLong);
                        if (creditResult == TransactionAttemptResult.Confirmed)
                        {
                            fallbackTotal = fallbackTotalLong;
                            paidItems.AddRange(fallbackItems);
                            paidButPending += fallbackItems.Count;
                        }
                        else
                        {
                            string reason = creditResult == TransactionAttemptResult.Uncertain ? "resultado do crédito incerto" : "crédito não aplicado";
                            warnings.Add(reason + "; " + fallbackItems.Count + " item(ns) mantido(s) no chão.");
                            Log.LogWarning("SellAll: " + fallbackItems.Count + " item(ns) sem crédito confirmado; mantidos no chão.");
                        }
                    }
                }

                if (unknownWorth > 0)
                    warnings.Add(unknownWorth + " item(ns) mantido(s): valor não reconhecido.");
                if (noNetworkRoute > 0)
                    warnings.Add(noNetworkRoute + " item(ns) mantido(s): estado ou rota de rede não confirmado.");
                if (uncertainCredit > 0)
                    warnings.Add(uncertainCredit + " item(ns) com crédito incerto; mantidos no chão.");

                var toDespawn = new List<GroundItem>(paidItems.Count + cleanupItems.Count);
                toDespawn.AddRange(paidItems);
                toDespawn.AddRange(cleanupItems);
                if (toDespawn.Count == 0)
                {
                    _running = false;
                    Log.LogInfo("SellAll: " + items.Count + " candidato(s), nada vendido ou removido.");
                    ShowHud(0, 0, CombineWarnings(warnings));
                    return;
                }

                var paidIds = new HashSet<int>();
                foreach (var item in paidItems) paidIds.Add(item.InstanceId);
                paidButPending = paidItems.Count;
                int candidates = items.Count;
                long creditedTotal = nativeTotal + fallbackTotal;
                Log.LogInfo("SellAll: " + candidates + " candidato(s), crédito confirmado $" + creditedTotal + "; iniciando despawn de " + toDespawn.Count + " item(ns).");

                StartCoroutine(Despawner.DespawnBatch(toDespawn, Cfg.LimitePorFrame.Value, result =>
                {
                    _running = false;
                    int sold = 0;
                    int removed = 0;
                    int paidButNotRemoved = 0;
                    int cleanupFailed = 0;

                    foreach (var record in result.Removed)
                    {
                        if (paidIds.Contains(record.Item.InstanceId)) sold++;
                        else removed++;
                    }
                    foreach (var record in result.Failed)
                    {
                        if (paidIds.Contains(record.Item.InstanceId)) paidButNotRemoved++;
                        else cleanupFailed++;
                        Log.LogWarning("SellAll: despawn falhou para '" + record.Item.Name + "' após " + record.Attempts + " tentativa(s): " + record.Reason + (paidIds.Contains(record.Item.InstanceId) ? "; crédito já aplicado." : "; item sem venda mantido."));
                    }

                    var finalWarnings = new List<string>();
                    if (paidButNotRemoved > 0)
                        finalWarnings.Add("Crédito aplicado, mas " + paidButNotRemoved + " item(ns) ficaram no chão.");
                    if (cleanupFailed > 0)
                        finalWarnings.Add(cleanupFailed + " item(ns) sem venda não foram removidos.");
                    finalWarnings.AddRange(warnings);

                    Log.LogInfo("SellAll concluído: vendidos=" + sold + ", removidos sem venda=" + removed + ", falhas=" + result.Failed.Count + ", crédito confirmado=$" + creditedTotal + ".");
                    ShowHud(sold, removed, CombineWarnings(finalWarnings));
                }));
                paidButPending = 0; // a coroutine agora é responsável por concluir e informar estes itens
            }
            catch (System.Exception e)
            {
                _running = false;
                Log.LogError("SellAll falhou: " + e);
                string warning = paidButPending > 0
                    ? "Crédito aplicado; remoção interrompida para " + paidButPending + " item(ns). Confira o chão."
                    : "A limpeza falhou; confira o log.";
                ShowHud(0, 0, warning);
            }
        }

        private static string CombineWarnings(List<string> warnings)
        {
            if (warnings.Count == 0) return "";
            if (warnings.Count == 1) return warnings[0];
            return warnings[0] + " (mais " + (warnings.Count - 1) + " aviso(s); confira o log).";
        }

        private void ShowHud(int sold, int removed, string warning)
        {
            _hudMessage = "Vendidos: " + sold + " | Removidos: " + removed;
            _hudWarning = warning;
            _hudMessageUntil = Time.unscaledTime + 3f;
        }

        private void ShowStatus(string message, float duration)
        {
            _hudMessage = message;
            _hudWarning = "";
            _hudMessageUntil = Time.unscaledTime + duration;
        }

        private bool ShowBlockedFeedback(string message, string category)
        {
            float now = Time.unscaledTime;
            if (now < _nextBlockedFeedbackAt && _lastBlockedFeedback == category) return false;
            _nextBlockedFeedbackAt = now + 0.75f;
            _lastBlockedFeedback = category;
            ShowStatus(message, 1.1f);
            return true;
        }

        private void OnGUI()
        {
            if (Time.unscaledTime >= _hudMessageUntil || string.IsNullOrEmpty(_hudMessage)) return;

            float width = Mathf.Max(1f, Mathf.Min(320f, Screen.width - 32f));
            bool hasWarning = !string.IsNullOrEmpty(_hudWarning);
            float height = hasWarning ? 54f : 30f;
            var rect = new Rect(Mathf.Max(16f, Screen.width - width - 16f), 20f, width, height);
            Color previousColor = GUI.color;
            GUI.color = new Color(0f, 0f, 0f, 0.32f);
            GUI.DrawTexture(rect, Texture2D.whiteTexture);
            GUI.color = new Color(1f, 1f, 1f, 0.88f);
            _hudStyle ??= new GUIStyle(GUI.skin.label)
            {
                alignment = TextAnchor.MiddleCenter,
                fontSize = 13,
                fontStyle = FontStyle.Normal
            };
            GUI.Label(new Rect(rect.x + 6f, rect.y, rect.width - 12f, 28f), _hudMessage, _hudStyle);

            if (hasWarning)
            {
                GUI.color = new Color(1f, 0.82f, 0.58f, 0.92f);
                _hudWarningStyle ??= new GUIStyle(GUI.skin.label)
                {
                    alignment = TextAnchor.MiddleCenter,
                    fontSize = 11,
                    wordWrap = true
                };
                GUI.Label(new Rect(rect.x + 8f, rect.y + 26f, rect.width - 16f, rect.height - 27f), _hudWarning, _hudWarningStyle);
            }
            GUI.color = previousColor;
        }
    }
}
