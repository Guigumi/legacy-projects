using System;
using System.Reflection;
using UnityEngine;

namespace SellAllFloorFix
{
    internal enum TransactionAttemptResult { Unavailable, Confirmed, Uncertain }

    internal static class Seller
    {
        private static readonly string[] SellMethodNames = { "Sell", "SellItem", "CmdSell", "ServerSell", "SellToShop" };
        private static readonly string[] CreditMethodNames = { "AddMoney", "Add", "GiveMoney", "AddCoins" };
        private static readonly string[] LocalPlayerFlagNames = { "IsLocalPlayer", "isLocalPlayer", "IsLocal", "isLocal", "IsOwner", "isOwner", "IsMine", "isMine", "IsMainPlayer", "isMainPlayer", "IsClient", "isClient" };

        public static TransactionAttemptResult TryNativeSell(Component item)
        {
            var itemType = item.GetType();
            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                Type? mmType = null;
                try { mmType = asm.GetType("MoneyManager"); } catch { continue; }
                if (mmType == null) continue;
                foreach (var m in mmType.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static))
                {
                    if (m.Name != "SellItem") continue;
                    var ps = m.GetParameters();
                    if (ps.Length != 1 || !ps[0].ParameterType.IsAssignableFrom(itemType)) continue;
                    try { m.Invoke(null, new object[] { item }); return TransactionAttemptResult.Confirmed; }
                    catch (Exception e)
                    {
                        Plugin.Log.LogWarning("SellAll: rota nativa de venda ficou incerta para '" + item.name + "': " + e.GetBaseException().Message);
                        return TransactionAttemptResult.Uncertain;
                    }
                }
            }

            // Só procurar rota legada quando nenhuma rota nativa compatível foi encontrada.
            foreach (var n in SellMethodNames)
            {
                var m = itemType.GetMethod(n, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance, null, Type.EmptyTypes, null);
                if (m == null) continue;
                try { m.Invoke(item, null); return TransactionAttemptResult.Confirmed; }
                catch (Exception e)
                {
                    Plugin.Log.LogWarning("SellAll: rota nativa " + n + " ficou incerta para '" + item.name + "': " + e.GetBaseException().Message);
                    return TransactionAttemptResult.Uncertain;
                }
            }
            return TransactionAttemptResult.Unavailable;
        }

        public static TransactionAttemptResult Credit(int total)
        {
            if (total <= 0) return TransactionAttemptResult.Confirmed;
            var result = TryCreditViaMoneyManager(total);
            if (result == TransactionAttemptResult.Unavailable)
                Plugin.Log.LogWarning("SellAll: rota de crédito indisponível ($" + total + "); itens mantidos no chão.");
            else if (result == TransactionAttemptResult.Uncertain)
                Plugin.Log.LogWarning("SellAll: resultado do crédito incerto ($" + total + "); itens mantidos e crédito não será repetido.");
            return result;
        }

        private static TransactionAttemptResult TryCreditViaMoneyManager(int total)
        {
            Type? playerType = FindPlayerType();
            object? localPlayer = playerType != null ? ResolveLocalPlayer(playerType) : null;
            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                Type? mmType = null;
                try { mmType = asm.GetType("MoneyManager"); } catch { continue; }
                if (mmType == null) continue;
                // 1) Rota real: AddMoney(int, Player) estático (ver inspection-notes.md).
                if (playerType != null && localPlayer != null)
                {
                    foreach (var m in mmType.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static))
                    {
                        if (m.Name != "AddMoney") continue;
                        var ps = m.GetParameters();
                        if (ps.Length != 2) continue;
                        if (ps[0].ParameterType != typeof(int)) continue;
                        if (!ps[1].ParameterType.IsAssignableFrom(playerType)) continue;
                        return InvokeCredit(m, null, new object[] { total, localPlayer }, "AddMoney(int,Player) estático", total);
                    }
                    // 2) Rota real via instância singleton: Instance.AddMoney(total, player).
                    try
                    {
                        object? inst = GetMoneyManagerInstance(mmType);
                        if (inst != null)
                        {
                            foreach (var m in mmType.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance))
                            {
                                if (m.Name != "AddMoney") continue;
                                var ps = m.GetParameters();
                                if (ps.Length != 2) continue;
                                if (ps[0].ParameterType != typeof(int)) continue;
                                if (!ps[1].ParameterType.IsAssignableFrom(playerType)) continue;
                                return InvokeCredit(m, inst, new object[] { total, localPlayer }, "AddMoney(int,Player) instância", total);
                            }
                        }
                    }
                    catch (Exception e) { Plugin.Log.LogDebug("MoneyManager instância (int,Player) falhou: " + e.GetBaseException().Message); }
                }
                else if (playerType != null)
                {
                    Plugin.Log.LogDebug("SellAll: Player local não resolvido; tentando fallbacks single-int.");
                }
                // 3) Fallbacks single-int (legado): estático AddMoney(int) / Add(int) / ...
                foreach (var mn in CreditMethodNames)
                {
                    var m = mmType.GetMethod(mn, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static, null, new[] { typeof(int) }, null);
                    if (m == null) continue;
                    return InvokeCredit(m, null, new object[] { total }, mn + " estático", total);
                }
                // 4) Fallbacks single-int (legado): instância singleton.
                try
                {
                    object? inst = GetMoneyManagerInstance(mmType);
                    if (inst != null)
                    {
                        foreach (var mn in CreditMethodNames)
                        {
                            var m = mmType.GetMethod(mn, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance, null, new[] { typeof(int) }, null);
                            if (m == null) continue;
                            return InvokeCredit(m, inst, new object[] { total }, mn + " instância", total);
                        }
                    }
                }
                catch (Exception e) { Plugin.Log.LogDebug("MoneyManager instância falhou: " + e.GetBaseException().Message); }
            }
            return TransactionAttemptResult.Unavailable;
        }

        private static TransactionAttemptResult InvokeCredit(MethodInfo method, object? target, object[] args, string route, int total)
        {
            try
            {
                method.Invoke(target, args);
                AfterCreditFx(total);
                return TransactionAttemptResult.Confirmed;
            }
            catch (Exception e)
            {
                Plugin.Log.LogWarning("SellAll: " + route + " ficou incerto: " + e.GetBaseException().Message);
                return TransactionAttemptResult.Uncertain;
            }
        }

        private static Type? FindPlayerType()
        {
            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                try
                {
                    var t = asm.GetType("Player");
                    if (t != null) return t;
                }
                catch { }
            }
            Plugin.Log.LogDebug("SellAll: tipo Player não achado nos assemblies.");
            return null;
        }

        private static object? ResolveLocalPlayer(Type playerType)
        {
            UnityEngine.Object[] all;
            try { all = UnityEngine.Object.FindObjectsOfType(playerType); }
            catch (Exception e) { Plugin.Log.LogDebug("FindObjectsOfType(Player) falhou: " + e.GetBaseException().Message); return null; }
            if (all == null || all.Length == 0) return null;
            foreach (var o in all)
            {
                if (o == null) continue;
                if (HasLocalFlag(o)) return o;
            }
            return all[0]; // sem flag local determinável: primeiro achado
        }

        private static bool HasLocalFlag(object o)
        {
            var t = o.GetType();
            foreach (var n in LocalPlayerFlagNames)
            {
                try
                {
                    var f = t.GetField(n, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                    if (f != null && f.FieldType == typeof(bool) && (bool)f.GetValue(o)!) return true;
                    var p = t.GetProperty(n, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                    if (p != null && p.PropertyType == typeof(bool) && p.CanRead && (bool)p.GetValue(o, null)!) return true;
                }
                catch { }
            }
            return false;
        }

        private static object? GetMoneyManagerInstance(Type mmType)
        {
            var instProp = mmType.GetProperty("Instance", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static);
            if (instProp != null)
            {
                try
                {
                    var v = instProp.GetValue(null, null);
                    if (v != null) return v;
                }
                catch { }
            }
            var f = mmType.GetField("Instance", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static);
            if (f != null)
            {
                try
                {
                    var v = f.GetValue(null);
                    if (v != null) return v;
                }
                catch { }
            }
            try
            {
                var found = UnityEngine.Object.FindObjectOfType(mmType) as Component;
                if (found != null) return found;
            }
            catch { }
            return null;
        }

        private static void AfterCreditFx(int total)
        {
            try
            {
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    Type? ui = null;
                    try { ui = asm.GetType("PlayerUI"); } catch { continue; }
                    if (ui == null) continue;
                    // Invocar PlayerUI.SetMoney SOMENTE se existir overload single-int;
                    // senão pular (OnChangeMoney atualiza o HUD automaticamente).
                    var m = ui.GetMethod("SetMoney", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance, null, new[] { typeof(int) }, null);
                    if (m != null)
                    {
                        try
                        {
                            if (m.IsStatic) m.Invoke(null, new object[] { total });
                            else
                            {
                                var found = UnityEngine.Object.FindObjectOfType(ui) as Component;
                                if (found != null) m.Invoke(found, new object[] { total });
                            }
                        }
                        catch (Exception e) { Plugin.Log.LogDebug("SetMoney falhou: " + e.GetBaseException().Message); }
                    }
                    // MoneySound best-effort em try/catch.
                    try
                    {
                        Type? mm = null;
                        try { mm = asm.GetType("MoneyManager"); } catch { }
                        if (mm != null)
                        {
                            foreach (var snd in mm.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance))
                            {
                                if (snd.Name != "MoneySound") continue;
                                if (snd.GetParameters().Length != 0) continue; // overloads (bool,Player) exigem Player: pular com segurança
                                if (snd.IsStatic) snd.Invoke(null, null);
                                else
                                {
                                    var foundMm = UnityEngine.Object.FindObjectOfType(mm) as Component;
                                    if (foundMm != null) snd.Invoke(foundMm, null);
                                }
                                break;
                            }
                        }
                    }
                    catch (Exception e) { Plugin.Log.LogDebug("MoneySound falhou: " + e.GetBaseException().Message); }
                    break;
                }
            }
            catch (Exception e) { Plugin.Log.LogDebug("FX pós-crédito falhou: " + e.GetBaseException().Message); }
            Plugin.Log.LogInfo("SellAll: creditado $" + total);
        }
    }
}
