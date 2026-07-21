using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using System.Text.Json;

var dir = args.Length > 0 ? args[0] : Directory.GetCurrentDirectory();
var jOpts = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };
var results = new Dictionary<string, FileResult>();

foreach (var file in Directory.EnumerateFiles(dir, "*.cs", SearchOption.AllDirectories))
{
    var rel = Path.GetRelativePath(dir, file).Replace('\\', '/');
    try
    {
        var source = File.ReadAllText(file);
        var tree = CSharpSyntaxTree.ParseText(source);
        var root = tree.GetRoot();

        var symbols = new List<SymbolInfo>();
        var typeRefs = new HashSet<string>();

        foreach (var node in root.DescendantNodes())
        {
            var span = tree.GetLineSpan(node.Span);
            int s = span.StartLinePosition.Line + 1;
            int e = span.EndLinePosition.Line + 1;

            switch (node)
            {
                case ClassDeclarationSyntax c:
                    symbols.Add(new(c.Identifier.Text, "class", s, e));
                    AddBaseTypes(typeRefs, c.BaseList);
                    break;
                case InterfaceDeclarationSyntax i:
                    symbols.Add(new(i.Identifier.Text, "interface", s, e));
                    AddBaseTypes(typeRefs, i.BaseList);
                    break;
                case RecordDeclarationSyntax r:
                    symbols.Add(new(r.Identifier.Text, "record", s, e));
                    AddBaseTypes(typeRefs, r.BaseList);
                    break;
                case StructDeclarationSyntax st:
                    symbols.Add(new(st.Identifier.Text, "struct", s, e));
                    AddBaseTypes(typeRefs, st.BaseList);
                    break;
                case EnumDeclarationSyntax en:
                    symbols.Add(new(en.Identifier.Text, "enum", s, e));
                    break;
                case MethodDeclarationSyntax m:
                    symbols.Add(new(m.Identifier.Text, "method", s, e));
                    AddTypeName(typeRefs, m.ReturnType);
                    foreach (var p in m.ParameterList.Parameters)
                        if (p.Type is not null) AddTypeName(typeRefs, p.Type);
                    break;
                case ConstructorDeclarationSyntax ctor:
                    symbols.Add(new(ctor.Identifier.Text, "constructor", s, e));
                    foreach (var p in ctor.ParameterList.Parameters)
                        if (p.Type is not null) AddTypeName(typeRefs, p.Type);
                    break;
                case PropertyDeclarationSyntax prop:
                    symbols.Add(new(prop.Identifier.Text, "property", s, e));
                    AddTypeName(typeRefs, prop.Type);
                    break;
                case FieldDeclarationSyntax f:
                    AddTypeName(typeRefs, f.Declaration.Type);
                    break;
                case ObjectCreationExpressionSyntax obj:
                    AddTypeName(typeRefs, obj.Type);
                    break;
            }
        }

        results[rel] = new FileResult(symbols, typeRefs.ToList());
    }
    catch { /* skip unparseable files */ }
}

Console.WriteLine(JsonSerializer.Serialize(results, jOpts));

void AddBaseTypes(HashSet<string> refs, BaseListSyntax? baseList)
{
    if (baseList is null) return;
    foreach (var bt in baseList.Types)
        AddTypeName(refs, bt.Type);
}

void AddTypeName(HashSet<string> refs, TypeSyntax type)
{
    switch (type)
    {
        case IdentifierNameSyntax id when !IsPrimitive(id.Identifier.Text):
            refs.Add(id.Identifier.Text);
            break;
        case GenericNameSyntax gen:
            if (!IsPrimitive(gen.Identifier.Text)) refs.Add(gen.Identifier.Text);
            foreach (var arg in gen.TypeArgumentList.Arguments) AddTypeName(refs, arg);
            break;
        case QualifiedNameSyntax q:
            AddTypeName(refs, q.Right);
            break;
        case NullableTypeSyntax n:
            AddTypeName(refs, n.ElementType);
            break;
        case ArrayTypeSyntax a:
            AddTypeName(refs, a.ElementType);
            break;
    }
}

bool IsPrimitive(string n) => n is
    "void" or "string" or "int" or "long" or "double" or "float" or "bool"
    or "byte" or "char" or "object" or "decimal" or "short" or "uint" or "ulong"
    or "ushort" or "sbyte" or "nint" or "nuint" or "var" or "dynamic"
    or "String" or "Int32" or "Int64" or "Boolean" or "Double" or "Object" or "Void"
    or "Byte" or "Char" or "Decimal" or "Single" or "DateTime" or "DateTimeOffset"
    or "Guid" or "TimeSpan" or "Uri";

record SymbolInfo(string Name, string Kind, int StartLine, int EndLine);
record FileResult(List<SymbolInfo> Symbols, List<string> TypeRefs);
