using System;
using System.Collections.Generic;
using Autodesk.Revit.DB;

namespace RookBim.Revit
{
    internal static class RevitParameterSerializer
    {
        public static IReadOnlyList<object> Serialize(Element element)
        {
            var result = new List<object>();
            SerializeParameters(result, element, "instance");

            var typeId = element.GetTypeId();
            if (typeId != ElementId.InvalidElementId)
            {
                var type = element.Document?.GetElement(typeId);
                if (type != null)
                {
                    SerializeParameters(result, type, "type");
                }
            }

            return result;
        }

        private static void SerializeParameters(
            ICollection<object> result,
            Element owner,
            string source)
        {
            foreach (Parameter parameter in owner.Parameters)
            {
                var definition = parameter.Definition;
                result.Add(new
                {
                    source = source,
                    ownerElementId = ToInt32OrNull(owner.Id),
                    ownerUniqueId = NullIfWhiteSpace(owner.UniqueId),
                    name = definition?.Name ?? string.Empty,
                    storageType = parameter.StorageType.ToString(),
                    displayValue = DisplayValue(parameter),
                    rawValue = RawValue(parameter),
                    isReadOnly = parameter.IsReadOnly,
                    builtIn = TryBuiltInName(parameter),
                    guid = TryGuid(parameter),
                    canCompareNumeric = false
                });
            }
        }

        private static string? DisplayValue(Parameter parameter)
        {
            return parameter.AsValueString() ?? parameter.AsString();
        }

        private static object? RawValue(Parameter parameter)
        {
            switch (parameter.StorageType)
            {
                case StorageType.String:
                    return parameter.AsString();
                case StorageType.Integer:
                    return parameter.AsInteger();
                case StorageType.Double:
                    return parameter.AsDouble();
                case StorageType.ElementId:
                    return ToInt32OrNull(parameter.AsElementId());
                default:
                    return null;
            }
        }

        private static string? TryBuiltInName(Parameter parameter)
        {
            var builtIn = (parameter.Definition as InternalDefinition)?.BuiltInParameter;
            return builtIn.HasValue ? builtIn.Value.ToString() : null;
        }

        private static string? TryGuid(Parameter parameter)
        {
            try
            {
                var guid = parameter.GUID;
                return guid == Guid.Empty ? null : guid.ToString("D");
            }
            catch (Autodesk.Revit.Exceptions.InvalidOperationException)
            {
                return null;
            }
        }

        private static int? ToInt32OrNull(ElementId? id)
        {
            if (id == null)
            {
                return null;
            }

            var value = id.Value;
            if (value < int.MinValue || value > int.MaxValue)
            {
                return null;
            }

            return (int)value;
        }

        private static string? NullIfWhiteSpace(string? value)
        {
            return string.IsNullOrWhiteSpace(value) ? null : value;
        }
    }
}
