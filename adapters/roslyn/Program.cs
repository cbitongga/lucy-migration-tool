using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

// Optional semantic evidence adapter. It does not evaluate an MSBuild solution.
// Missing references, generated code, and conditional variants remain explicit.
string Required(string key) {
    int i = Array.IndexOf(args, key);
    if (i < 0 || i + 1 >= args.Length) throw new ArgumentException("Missing " + key);
    return args[i + 1];
}
IEnumerable<string> Values(string key) {
    for (int i = 0; i + 1 < args.Length; i++) if (args[i] == key) yield return args[i + 1];
}
string Hash(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();
string root = Path.GetFullPath(Required("--root"));
string rootId = Required("--root-id");
var ignored = new HashSet<string>(new[] { "bin", "obj", ".git", "node_modules" });
var options = new EnumerationOptions { RecurseSubdirectories = true, AttributesToSkip = FileAttributes.ReparsePoint, IgnoreInaccessible = false };
var paths = Directory.EnumerateFiles(root, "*.cs", options)
    .Where(p => !Path.GetRelativePath(root, p).Split(Path.DirectorySeparatorChar).Any(ignored.Contains)).Order().ToArray();
var parse = CSharpParseOptions.Default.WithPreprocessorSymbols(Values("--define"));
var trees = paths.Select(p => CSharpSyntaxTree.ParseText(File.ReadAllText(p), parse, p)).ToArray();
var refs = ((string?)AppContext.GetData("TRUSTED_PLATFORM_ASSEMBLIES") ?? "")
    .Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries).Concat(Values("--reference"))
    .Distinct().Select(p => MetadataReference.CreateFromFile(Path.GetFullPath(p)));
var compilation = CSharpCompilation.Create("MigrationEvidence", trees, refs,
    new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary));
var nodes = new List<object>();
var edges = new List<object>();
var unresolved = new List<object>();
var symbolIds = new Dictionary<ISymbol, string>(SymbolEqualityComparer.Default);
object Ref(SyntaxNode syntax) {
    var span = syntax.GetLocation().GetLineSpan();
    return new { root = rootId, path = Path.GetRelativePath(root, span.Path).Replace('\\', '/'),
        start = span.StartLinePosition.Line + 1, end = span.EndLinePosition.Line + 1 };
}
foreach (var tree in trees) {
    var model = compilation.GetSemanticModel(tree);
    foreach (var syntax in tree.GetRoot().DescendantNodes().Where(n =>
        n is BaseTypeDeclarationSyntax or BaseMethodDeclarationSyntax or PropertyDeclarationSyntax)) {
        var symbol = model.GetDeclaredSymbol(syntax);
        if (symbol == null) continue;
        string label = symbol.ToDisplayString(SymbolDisplayFormat.CSharpErrorMessageFormat);
        string id = "S" + Hash(label + tree.FilePath + syntax.SpanStart)[..20];
        symbolIds[symbol.OriginalDefinition] = id;
        nodes.Add(new { id, kind = symbol.Kind.ToString(), label, @ref = Ref(syntax),
            sha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(tree.FilePath))).ToLowerInvariant(),
            confidence = "roslyn_declaration" });
    }
}
foreach (var tree in trees) {
    var model = compilation.GetSemanticModel(tree);
    foreach (var call in tree.GetRoot().DescendantNodes().OfType<InvocationExpressionSyntax>()) {
        var info = model.GetSymbolInfo(call);
        var owner = model.GetEnclosingSymbol(call.SpanStart);
        var target = info.Symbol;
        if (owner != null && target != null &&
            symbolIds.TryGetValue(owner.OriginalDefinition, out var from) &&
            symbolIds.TryGetValue(target.OriginalDefinition, out var to))
            edges.Add(new { source = from, target = to, relation = "calls", confidence = "roslyn_resolved", @ref = Ref(call) });
        else
            unresolved.Add(new { @ref = Ref(call), expression = call.Expression.ToString(),
                reason = target == null ? info.CandidateReason.ToString() : "external_or_unmapped_symbol" });
    }
}
var diagnostics = compilation.GetDiagnostics().Where(d => d.Severity == DiagnosticSeverity.Error)
    .Select(d => new { id = d.Id, message = d.GetMessage(), location = d.Location.ToString() }).ToArray();
Console.WriteLine(JsonSerializer.Serialize(new {
    schema_version = 1, adapter = "roslyn", nodes, edges, unresolved, diagnostics,
    semantic_complete = false,
    limits = new[] { "Standalone compilation; not MSBuildWorkspace evaluation.",
        "Supply matching dependency references and defines; generated sources and other build variants require separate runs.",
        "A bound call edge is evidence, not proof of behavioral equivalence." }
}));
