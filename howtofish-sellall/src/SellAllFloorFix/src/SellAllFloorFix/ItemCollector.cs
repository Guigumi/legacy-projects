using System;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;

namespace SellAllFloorFix
{
    internal readonly struct GroundItem
    {
        public readonly GameObject Go;
        public readonly int Worth;
        public readonly bool WorthKnown;
        public readonly Component Component;
        public readonly object? NetObj;
        public readonly string Name;
        public readonly int InstanceId;

        public GroundItem(GameObject go, int worth, bool worthKnown, Component comp, object? netObj)
        {
            Go = go;
            Worth = worth;
            WorthKnown = worthKnown;
            Component = comp;
            NetObj = netObj;
            Name = go != null ? go.name : "?";
            InstanceId = go != null ? go.GetInstanceID() : 0;
        }
    }

    internal readonly struct WorthRead
    {
        public readonly bool Known;
        public readonly int Value;

        public WorthRead(bool known, int value)
        {
            Known = known;
            Value = value;
        }
    }

    internal static class ItemCollector
    {
        private static readonly string[] ItemTypeNames = { "Item", "Creature" };
        private static readonly string[] WorthNames = { "TotalWorth", "DefaultWorth", "Worth", "worth", "price", "Price", "value", "Value", "sellPrice", "SellPrice" };
        private static readonly string[] HeldNames = { "HasPlayerHolder", "IsInInventory", "isHeld", "IsHeld", "held", "Held", "inHand", "InHand", "equipped", "Equipped" };

        public static List<GroundItem> Collect()
        {
            var out_ = new List<GroundItem>(128);
            var seen = new HashSet<int>();
            var behaviours = UnityEngine.Object.FindObjectsOfType<MonoBehaviour>();
            foreach (var b in behaviours)
            {
                if (b == null) continue;
                var t = b.GetType();
                if (!IsItemType(t)) continue;
                var go = b.gameObject;
                if (go == null || !go.activeInHierarchy) continue;
                if (IsHeld(b)) continue;
                int instanceId = go.GetInstanceID();
                if (!seen.Add(instanceId)) continue;
                WorthRead worth = ReadWorth(b);
                object? netObj = FindNetworkObject(go);
                if (netObj == null)
                {
                    Plugin.Log.LogDebug("SellAll: '" + go.name + "' sem NetworkObject; será mantido.");
                }
                out_.Add(new GroundItem(go, worth.Value, worth.Known, b, netObj));
            }
            return out_;
        }

        private static bool IsItemType(Type t)
        {
            string name = t.Name;
            foreach (var n in ItemTypeNames)
                if (name == n || t.FullName == n)
                    return true;
            // Herança: Creature costuma herdar de Item — aceita subclasses cujo base se chame Item
            var bt = t.BaseType;
            while (bt != null && bt != typeof(object) && bt != typeof(MonoBehaviour) && bt != typeof(Component))
            {
                if (bt.Name == "Item") return true;
                bt = bt.BaseType;
            }
            return false;
        }

        private static bool IsHeld(Component c)
        {
            var t = c.GetType();
            foreach (var n in HeldNames)
            {
                var f = t.GetField(n, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                if (f != null && f.FieldType == typeof(bool))
                {
                    try { if ((bool)f.GetValue(c)!) return true; } catch { }
                }
                var p = t.GetProperty(n, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                if (p != null && p.PropertyType == typeof(bool) && p.CanRead)
                {
                    try { if ((bool)p.GetValue(c, null)!) return true; } catch { }
                }
            }
            // Segurança extra: se o objeto está parentado a um Player, considera segurado
            var parent = c.transform?.parent;
            while (parent != null)
            {
                if (parent.name.IndexOf("player", StringComparison.OrdinalIgnoreCase) >= 0
                    || parent.name.IndexOf("hand", StringComparison.OrdinalIgnoreCase) >= 0)
                    return true;
                parent = parent.parent;
            }
            return false;
        }

        private static WorthRead ReadWorth(Component c)
        {
            var t = c.GetType();
            foreach (var n in WorthNames)
            {
                var f = t.GetField(n, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                if (f != null)
                {
                    try
                    {
                        object? v = f.GetValue(c);
                        if (TryConvertWorth(v, out int value)) return new WorthRead(true, value);
                    }
                    catch { }
                }
                var p = t.GetProperty(n, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                if (p != null && p.CanRead)
                {
                    try
                    {
                        object? v = p.GetValue(c, null);
                        if (TryConvertWorth(v, out int value)) return new WorthRead(true, value);
                    }
                    catch { }
                }
            }
            return new WorthRead(false, 0);
        }

        private static bool TryConvertWorth(object? value, out int worth)
        {
            switch (value)
            {
                case int i:
                    worth = i;
                    return true;
                case float f when !float.IsNaN(f) && !float.IsInfinity(f):
                    worth = Mathf.RoundToInt(f);
                    return true;
                case double d when !double.IsNaN(d) && !double.IsInfinity(d):
                    worth = (int)Math.Round(d);
                    return true;
                default:
                    worth = 0;
                    return false;
            }
        }

        private static object? FindNetworkObject(GameObject go)
        {
            // Mesmo GameObject, depois pais, depois filhos: cobre root NetworkObject + Item visual filho.
            foreach (var c in go.GetComponents<Component>())
            {
                if (IsNetworkObject(c)) return c;
            }
            foreach (var c in go.GetComponentsInParent<Component>(true))
            {
                if (IsNetworkObject(c)) return c;
            }
            foreach (var c in go.GetComponentsInChildren<Component>(true))
            {
                if (IsNetworkObject(c)) return c;
            }
            return null;
        }

        private static bool IsNetworkObject(Component? c)
        {
            return c != null && c.GetType().Name == "NetworkObject";
        }
    }
}
