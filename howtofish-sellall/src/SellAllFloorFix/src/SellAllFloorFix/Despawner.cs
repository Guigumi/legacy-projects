using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;

namespace SellAllFloorFix
{
    internal enum NetworkSpawnState { Unknown, Spawned, Despawned }

    internal readonly struct DespawnRecord
    {
        public readonly GroundItem Item;
        public readonly int Attempts;
        public readonly string Reason;

        public DespawnRecord(GroundItem item, int attempts, string reason)
        {
            Item = item;
            Attempts = attempts;
            Reason = reason;
        }
    }

    internal sealed class DespawnBatchResult
    {
        public readonly List<DespawnRecord> Removed = new List<DespawnRecord>();
        public readonly List<DespawnRecord> Failed = new List<DespawnRecord>();
    }

    internal static class Despawner
    {
        private sealed class PendingDespawn
        {
            public GroundItem Item { get; }
            public int Attempts { get; set; }

            public PendingDespawn(GroundItem item) { Item = item; }
        }

        public static bool IsServer()
        {
            try
            {
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    // (1) Qualquer NetworkBehaviour -> IsServer / IsServerInitialized.
                    Type? nb = null;
                    try { nb = asm.GetType("FishNet.Object.NetworkBehaviour"); } catch { nb = null; }
                    if (nb != null)
                    {
                        Component? inst = null;
                        try { inst = UnityEngine.Object.FindObjectOfType(nb) as Component; } catch { inst = null; }
                        if (inst != null)
                        {
                            var p1 = nb.GetProperty("IsServer", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                            if (p1 != null && p1.PropertyType == typeof(bool) && p1.CanRead)
                            {
                                try { return (bool)p1.GetValue(inst, null)!; } catch { }
                            }
                            var p2 = nb.GetProperty("IsServerInitialized", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                            if (p2 != null && p2.PropertyType == typeof(bool) && p2.CanRead)
                            {
                                try { return (bool)p2.GetValue(inst, null)!; } catch { }
                            }
                        }
                    }
                    // (1b) MoneyManager também é NetworkBehaviour: checar direto.
                    Type? mm = null;
                    try { mm = asm.GetType("MoneyManager"); } catch { mm = null; }
                    if (mm != null)
                    {
                        Component? minst = null;
                        try { minst = UnityEngine.Object.FindObjectOfType(mm) as Component; } catch { minst = null; }
                        if (minst != null)
                        {
                            var p1 = mm.GetProperty("IsServer", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                            if (p1 != null && p1.PropertyType == typeof(bool) && p1.CanRead)
                            {
                                try { return (bool)p1.GetValue(minst, null)!; } catch { }
                            }
                            var p2 = mm.GetProperty("IsServerInitialized", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                            if (p2 != null && p2.PropertyType == typeof(bool) && p2.CanRead)
                            {
                                try { return (bool)p2.GetValue(minst, null)!; } catch { }
                            }
                        }
                    }
                    // (2) NetworkManager.IsServer / IsServerStarted.
                    Type? nm = null;
                    try { nm = asm.GetType("FishNet.Managing.NetworkManager"); } catch { nm = null; }
                    if (nm != null)
                    {
                        Component? ninst = null;
                        try { ninst = UnityEngine.Object.FindObjectOfType(nm) as Component; } catch { ninst = null; }
                        if (ninst != null)
                        {
                            var p1 = nm.GetProperty("IsServer", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static);
                            if (p1 != null && p1.PropertyType == typeof(bool) && p1.CanRead && p1.GetGetMethod(true) != null)
                            {
                                try { return (bool)p1.GetValue(p1.GetGetMethod(true)!.IsStatic ? null : ninst, null)!; } catch { }
                            }
                            var p2 = nm.GetProperty("IsServerStarted", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static);
                            if (p2 != null && p2.PropertyType == typeof(bool) && p2.CanRead && p2.GetGetMethod(true) != null)
                            {
                                try { return (bool)p2.GetValue(p2.GetGetMethod(true)!.IsStatic ? null : ninst, null)!; } catch { }
                            }
                        }
                    }
                }
                // (2b) Fallback estático: FishNet.InstanceFinder.NetworkManager (ver inspection-notes.md).
                // IsServer mora no NetworkManager, não no InstanceFinder direto.
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    Type? finder = null;
                    try { finder = asm.GetType("FishNet.InstanceFinder"); } catch { continue; }
                    if (finder == null) continue;
                    PropertyInfo? nmProp = null;
                    try { nmProp = finder.GetProperty("NetworkManager", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static); } catch { continue; }
                    if (nmProp == null || !nmProp.CanRead || nmProp.GetGetMethod(true) == null) continue;
                    object? nmInst = null;
                    try { nmInst = nmProp.GetValue(null, null); } catch { continue; }
                    if (nmInst == null) continue;
                    var nmType = nmInst.GetType();
                    foreach (var pn in new[] { "IsServer", "IsServerStarted" })
                    {
                        var p = nmType.GetProperty(pn, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static);
                        if (p == null || p.PropertyType != typeof(bool) || !p.CanRead || p.GetGetMethod(true) == null) continue;
                        try { return (bool)p.GetValue(p.GetGetMethod(true)!.IsStatic ? null : nmInst, null)!; } catch { }
                    }
                }
            }
            catch (Exception e) { Plugin.Log.LogDebug("IsServer check falhou: " + e.GetBaseException().Message); }
            // (3) Default FALSE: autoridade indeterminável = sem venda (nenhum Despawn client-side).
            // NUNCA usar InstanceFinder.IsServer (inexistente).
            Plugin.Log.LogWarning("SellAll: autoridade de servidor indeterminável; assumindo CLIENTE (venda cancelada).");
            return false;
        }

        public static NetworkSpawnState GetSpawnState(GroundItem item)
        {
            if (item.Go == null) return NetworkSpawnState.Despawned;
            if (item.NetObj == null) return NetworkSpawnState.Unknown;
            try
            {
                var p = item.NetObj.GetType().GetProperty("IsSpawned", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                if (p == null || p.PropertyType != typeof(bool) || !p.CanRead) return NetworkSpawnState.Unknown;
                return (bool)p.GetValue(item.NetObj, null)! ? NetworkSpawnState.Spawned : NetworkSpawnState.Despawned;
            }
            catch (Exception e)
            {
                Plugin.Log.LogDebug("SellAll: leitura de IsSpawned falhou p/ '" + item.Name + "': " + e.GetBaseException().Message);
                return NetworkSpawnState.Unknown;
            }
        }

        public static bool CanDespawnNetwork(GroundItem item, out string reason)
        {
            if (item.Go == null) { reason = "objeto já destruído"; return false; }
            if (item.NetObj == null) { reason = "sem NetworkObject"; return false; }
            if (GetSpawnState(item) != NetworkSpawnState.Spawned)
            {
                reason = "estado de rede não confirmado como spawned";
                return false;
            }
            if (FindDespawnMethod(item.NetObj.GetType()) != null || FindServerManagerDespawn(out _, out _))
            {
                reason = "";
                return true;
            }
            reason = "método de despawn de rede indisponível";
            return false;
        }

        public static IEnumerator DespawnBatch(List<GroundItem> items, int perFrame, Action<DespawnBatchResult> onDone)
        {
            const int maxAttempts = 3; // tentativa inicial + duas novas tentativas
            int limit = Math.Max(1, perFrame);
            var result = new DespawnBatchResult();
            var pending = new List<PendingDespawn>();

            foreach (var item in items)
            {
                var state = GetSpawnState(item);
                if (state == NetworkSpawnState.Despawned)
                {
                    result.Removed.Add(new DespawnRecord(item, 0, "já despawnado"));
                    continue;
                }
                if (state != NetworkSpawnState.Spawned)
                {
                    result.Failed.Add(new DespawnRecord(item, 0, "estado de rede desconhecido"));
                    continue;
                }
                if (!CanDespawnNetwork(item, out string reason))
                {
                    result.Failed.Add(new DespawnRecord(item, 0, reason));
                    continue;
                }
                pending.Add(new PendingDespawn(item));
            }

            for (int attempt = 1; attempt <= maxAttempts && pending.Count > 0; attempt++)
            {
                int batch = 0;
                foreach (var current in pending)
                {
                    if (GetSpawnState(current.Item) != NetworkSpawnState.Spawned) continue;
                    RequestNetworkDespawn(current.Item);
                    current.Attempts++;
                    batch++;
                    if (batch >= limit)
                    {
                        batch = 0;
                        yield return null;
                    }
                }
                if (batch > 0) yield return null;

                var retry = new List<PendingDespawn>();
                foreach (var current in pending)
                {
                    var state = GetSpawnState(current.Item);
                    if (state == NetworkSpawnState.Despawned)
                    {
                        result.Removed.Add(new DespawnRecord(current.Item, current.Attempts, "despawn de rede confirmado"));
                    }
                    else if (state == NetworkSpawnState.Spawned && current.Attempts < maxAttempts)
                    {
                        retry.Add(current);
                    }
                    else
                    {
                        string reason = state == NetworkSpawnState.Unknown
                            ? "não foi possível confirmar o estado de rede"
                            : "continua spawned após " + current.Attempts + " tentativas";
                        result.Failed.Add(new DespawnRecord(current.Item, current.Attempts, reason));
                    }
                }
                pending = retry;
            }

            onDone(result);
        }

        private static bool RequestNetworkDespawn(GroundItem item)
        {
            try
            {
                var direct = FindDespawnMethod(item.NetObj!.GetType());
                if (direct != null)
                {
                    var ps = direct.GetParameters();
                    object?[]? args = ps.Length == 0 ? null : new object?[] { DefaultArg(ps[0]) };
                    direct.Invoke(item.NetObj, args);
                    return true;
                }

                if (FindServerManagerDespawn(out var manager, out var method))
                {
                    var ps = method.GetParameters();
                    object?[] args = ps.Length == 1
                        ? new object?[] { item.Go }
                        : new object?[] { item.Go, DefaultArg(ps[1]) };
                    method.Invoke(manager, args);
                    return true;
                }
            }
            catch (Exception e)
            {
                Plugin.Log.LogDebug("SellAll: pedido de despawn falhou p/ '" + item.Name + "': " + e.GetBaseException().Message);
                return false;
            }
            return false;
        }

        private static bool FindServerManagerDespawn(out object? manager, out MethodInfo method)
        {
            manager = null;
            method = null!;
            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                Type? sm = null;
                try { sm = asm.GetType("FishNet.Managing.Server.ServerManager") ?? asm.GetType("FishNet.Object.ServerManager"); }
                catch { continue; }
                if (sm == null) continue;
                Component? instance;
                try { instance = UnityEngine.Object.FindObjectOfType(sm) as Component; }
                catch { continue; }
                if (instance == null) continue;
                foreach (var candidate in sm.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance))
                {
                    if (candidate.Name != "Despawn") continue;
                    var ps = candidate.GetParameters();
                    if (ps.Length < 1 || ps.Length > 2 || ps[0].ParameterType != typeof(GameObject)) continue;
                    if (ps.Length == 2)
                    {
                        var pt = ps[1].ParameterType;
                        if (!ps[1].HasDefaultValue && !ps[1].IsOptional && Nullable.GetUnderlyingType(pt) == null
                            && pt.Name.IndexOf("DespawnType", StringComparison.OrdinalIgnoreCase) < 0) continue;
                    }
                    manager = instance;
                    method = candidate;
                    return true;
                }
            }
            return false;
        }

        private static MethodInfo? FindDespawnMethod(Type t)
        {
            MethodInfo? optional = null;
            foreach (var cand in t.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance))
            {
                if (cand.Name != "Despawn") continue;
                var ps = cand.GetParameters();
                if (ps.Length == 0) return cand;
                if (optional == null && ps.Length == 1)
                {
                    var pt = ps[0].ParameterType;
                    if (ps[0].HasDefaultValue || ps[0].IsOptional
                        || Nullable.GetUnderlyingType(pt) != null
                        || pt.Name.IndexOf("DespawnType", StringComparison.OrdinalIgnoreCase) >= 0)
                        optional = cand;
                }
            }
            return optional;
        }

        private static object? DefaultArg(ParameterInfo p)
        {
            try
            {
                if (p.HasDefaultValue) return p.DefaultValue;
            }
            catch { }
            var pt = p.ParameterType;
            if (!pt.IsValueType || Nullable.GetUnderlyingType(pt) != null) return null;
            return Activator.CreateInstance(pt);
        }
    }
}
