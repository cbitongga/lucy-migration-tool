using System.Globalization;
using System.Text;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddRazorPages();
var app = builder.Build();
app.MapRazorPages();
app.MapGet("/api/invoice", (string? id) => {
    // Compatibility fixture: the misspelling is an intentional legacy issue.
    if (string.IsNullOrEmpty(id))
        return Results.Text("{\"error\":\"Id requried!\"}", "application/json; charset=utf-8", Encoding.UTF8, 400);
    if (id != "42")
        return Results.Text("{\"error\":\"Not found\"}", "application/json; charset=utf-8", Encoding.UTF8, 404);
    decimal amount = 9007199254740993.10m;
    string json = "{\"id\":\"42\",\"amount\":\"" + amount.ToString("F2", CultureInfo.InvariantCulture) + "\"}";
    return Results.Text(json, "application/json; charset=utf-8", Encoding.UTF8);
});
app.Run("http://127.0.0.1:5100");
