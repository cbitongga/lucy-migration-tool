// Browser observations via an installed Playwright. No dependency downloads occur.
const fs = require('fs');
const crypto = require('crypto');

async function main() {
  const args = process.argv.slice(2);
  function arg(name) { const i=args.indexOf(name); if(i<0 || !args[i+1]) throw Error('Missing '+name); return args[i+1]; }
  const settings = JSON.parse(fs.readFileSync(arg('--config'), 'utf8'));
  const base = new URL(arg('--base'));
  if (!['http:', 'https:'].includes(base.protocol) || base.username || base.password) throw Error('Use an explicit test http(s) origin');
  if (!Array.isArray(settings.steps) || !settings.observations || !Object.keys(settings.observations).length) throw Error('Nonempty steps/observations required');
  const {chromium} = require('playwright');
  const browser = await chromium.launch({headless:true});
  try {
    const context = await browser.newContext({viewport:settings.viewport || {width:1280,height:800},
      locale:settings.locale || 'en-US', timezoneId:settings.timezone || 'UTC',
      reducedMotion:'reduce', serviceWorkers:'block'});
    // Isolated test-origin traffic only. Add other exact test origins explicitly.
    const allowed = new Set([base.origin, ...(settings.allowed_origins || [])]);
    await context.route('**/*', route => {
      const url = new URL(route.request().url());
      return allowed.has(url.origin) ? route.continue() : route.abort('blockedbyclient');
    });
    const page = await context.newPage();
    page.setDefaultTimeout(settings.timeout_ms || 5000);
    for (const step of settings.steps) {
      switch(step.action) {
        case 'goto': {
          const url = new URL(step.path, base);
          if (url.origin !== base.origin) throw Error('goto must stay on the configured test origin');
          const response = await page.goto(url.href, {waitUntil:'domcontentloaded'});
          if (!response || response.status() !== (step.expected_status || 200)) throw Error('Unexpected navigation status');
          break;
        }
        case 'fill': await page.locator(step.selector).fill(step.value); break;
        case 'click': await page.locator(step.selector).click(); break;
        case 'press': await page.locator(step.selector).press(step.key); break;
        case 'select': await page.locator(step.selector).selectOption(step.value); break;
        case 'check': await page.locator(step.selector).setChecked(step.checked); break;
        case 'wait': await page.locator(step.selector).waitFor({state:step.state || 'visible'}); break;
        default: throw Error('Unsupported browser action: '+step.action);
      }
    }
    const observations = {};
    for (const [id, spec] of Object.entries(settings.observations)) {
      if(spec.kind === 'path') { const u=new URL(page.url()); observations[id]=u.pathname+u.search+u.hash; continue; }
      if(spec.kind === 'screenshot_sha256') {
        const bytes = await page.screenshot({fullPage:!!spec.full_page, animations:'disabled', caret:'hide'});
        observations[id]=crypto.createHash('sha256').update(bytes).digest('hex'); continue;
      }
      const locator = page.locator(spec.selector);
      const count = await locator.count();
      if(spec.kind === 'count') { observations[id]=count; continue; }
      if(count !== 1) throw Error('Observation '+id+' must resolve exactly one element, got '+count);
      switch(spec.kind) {
        case 'text': observations[id]=await locator.textContent(); break;
        case 'value': observations[id]=await locator.inputValue(); break;
        case 'visible': observations[id]=await locator.isVisible(); break;
        case 'attribute': observations[id]=await locator.getAttribute(spec.name); break;
        default: throw Error('Unsupported observation kind: '+spec.kind);
      }
    }
    process.stdout.write(JSON.stringify({schema_version:1,dimension:'ui',observations})+'\n');
    await context.close();
  } finally { await browser.close(); }
}
main().catch(error => { process.stderr.write(error.message+'\n'); process.exitCode=1; });
