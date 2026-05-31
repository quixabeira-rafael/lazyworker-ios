# TODO — Ferramenta de Automação/QA iOS

Ferramenta para automação de tarefas/QA em **dispositivos reais e simulador iOS**, capaz de
operar sobre **apps de produção** (terceiros, sem código-fonte), **sem integração com Xcode**.

## Contexto técnico (decidido)

- iOS não expõe injeção de eventos de UI fora do XCTest/Accessibility → toda automação de UI
  precisa de um *runner* assinado no device (tipicamente **WebDriverAgent**).
- Simulador: sem assinatura. Device real: WDA assinado uma vez (Apple ID grátis serve).
- Apps da App Store (ex.: WhatsApp) **não rodam no simulador** → device real obrigatório pra esses.

### Camada de runtime (a definir)
Candidatos para conversar com o device:
- **Appium (XCUITest)** — gestos mais ricos (W3C Actions, pinch, multi-touch), `page_source` (árvore XML), Appium Inspector.
- **Maestro** — fluxos YAML, anti-flakiness embutido, Maestro Studio (inspetor visual). Sem pinch/multi-touch robusto.
- **idb** — baixo nível, `ui describe-all` (árvore em JSON), gestos por coordenada. Bom pra runtime próprio.
- **WDA puro** — base de Appium/Maestro; só se construir camada própria.
- Suporte (não-UI): `simctl`, `devicectl`, `pymobiledevice3`, `go-ios`, `tidevice`.

## Arquitetura — 3 fases que se alimentam

```
Exploração  ──►  Robots (RobotPattern)  ──►  Assertion
 (descobre)        (abstrai/reaproveita)       (valida)
```

### Fase 1 — Exploração
- Mapear o app **sem conhecimento prévio**, dirigida por objetivo do usuário.
- Insumo: árvore de acessibilidade (idb/Appium) + screenshots a cada estado.
- Entender telas, elementos interativos e transições; planejar o caminho até o objetivo
  (busca/planejamento sobre um grafo de telas descoberto em runtime).
- Saída: **conhecimento estruturado** (telas, elementos, transições, caminho pro objetivo) — ainda não é script.

### Fase 2 — Robots (RobotPattern)
- Onde mora o **reaproveitamento total**.
- Robot encapsula uma tela/contexto e expõe **ações de alto nível**, escondendo seletores/gestos.
- Ex.: `LoginRobot.enterEmail().enterPassword().submit() -> HomeRobot`.
- Robot escrito uma vez é reusado por todo fluxo que passa por aquela tela; fluxo novo = composição de Robots + Robot novo só pro delta.
- A Fase 1 "compila" o conhecimento em Robots.
- Questões em aberto: fronteiras de um Robot (tela vs. fluxo), nomeação semântica das ações,
  deduplicação (detectar Robot já existente p/ reusar), encadeamento (retornar próximo Robot).

### Fase 3 — Assertion (depois, será estruturada com calma)
- Validar que o app se comportou como esperado, com **múltiplas estratégias**:
  - **Estrutural**: elemento/label visível na árvore de acessibilidade.
  - **Visual**: screenshot diff / template matching.
  - **Estado/side-effects**: ex. tráfego de rede (potencial uso do `mitm-tracker`).
  - **Semântica**: "a tela atual É a esperada" (chegamos no Robot certo).
- Robots são o lugar natural pra pendurar assertions (`HomeRobot.assertLoaded()`).

### Ciclo (feedback loop)
1. Explora uma vez → entende o app + caminho.
2. Cristaliza aprendizado em Robots reutilizáveis.
3. Próximo fluxo reusa Robots; só explora o *delta* (telas novas).
4. Asserta ao longo do caminho.
→ Biblioteca de Robots cresce; custo/tempo por novo fluxo diminui. O sistema "aprende" o app.

## Decisões de arquitetura em aberto

- [ ] **Quem dirige a exploração?** LLM-no-loop (flexível, lida com apps imprevistos) vs. heurística determinística.
- [ ] **Robots são código ou dados?** Arquivo de código versionável (Swift? DSL próprio?) vs. estrutura de dados (JSON/YAML) interpretada por runtime.
- [ ] **Linguagem/runtime do alvo:** por cima de Appium, idb, ou runtime próprio sobre WDA — define a linguagem natural dos Robots.

## Decisões já tomadas
- Runtime: **WDA puro via HTTP**.
- Linguagem: **Python 3.11+** (dev em 3.13). Build: hatchling. CLI instalável (`lazyworker`).
- Stack: httpx + pydantic v2 + typer; pytest + pytest-httpx + ruff + mypy.

## Estado atual (milestone 1 — concluído)
- [x] Scaffold do pacote (`src/lazyworker`) + tooling (pyproject, ruff/mypy/pytest, venv).
- [x] Cliente WDA tipado: `WdaClient` (status, create_session) + `Session`
      (source, screenshot, tap, swipe, deep_link, terminate, delete).
- [x] Modelos da árvore de acessibilidade com travessia agêntica (`walk`/`find`/`find_all`).
- [x] Config loader (`lazyworker.toml`, descoberta upward).
- [x] CLI read-only: `status`, `doctor`, `source`, `screenshot`.
- [x] 17 testes (HTTP mockado, sem device). ruff + mypy strict limpos.

## Milestone 2 — em progresso
- [x] **Camada de descoberta de devices** (`devices/`): modelo `Device` tipado,
      `CommandRunner` injetável, `SimulatorProvider` (simctl), `PhysicalDeviceProvider`
      (devicectl, USB/rede), `DeviceRegistry` agregador. CLI `lazyworker devices`.
      Validado ao vivo: acha simuladores + device físico real (rede, Developer Mode).
- [x] Seam de assinatura `SigningMode` (simulator/free/paid) no config — 3 hipóteses.
      Testar só simulator + free; paid fica code-ready e não-testado.

## Milestone 2 — simulador concluído (validado e2e ao vivo)
- [x] `bootstrap/`: `WdaProject`/`WdaProvisioner` (git clone), `WdaBuilder` (xcodebuild
      build-for-testing, sem assinatura), `WdaLauncher` (test-without-building detached),
      `SimulatorController` (simctl boot/shutdown), `readiness.wait_until_ready`,
      `RunState` (persistência), `BootstrapService` (orquestra bootstrap/up/down).
- [x] CLI `bootstrap`/`up`/`down`. `ProcessManager` injetável (detached + kill por pid).
- [x] Fix actions: `tap`/`swipe` migrados pra **W3C Actions API** (`/session/{id}/actions`);
      o endpoint legado `/wda/tap/0` não existe no WDA atual.
- [x] **E2E ao vivo (simulador iPhone 17 Pro, iOS 26.5)**: bootstrap → up → source (árvore
      real dos Ajustes) → tap (mudou de tela) → screenshot (PNG 1206x2622) → down (state limpo).
- [x] 36→ testes unitários (runner/process mockados). ruff + mypy strict limpos.

## Preflight (doctor) — concluído (validado ao vivo)
- [x] `doctor/`: módulo de diagnóstico. `CheckResult`/`CheckStatus`/`DoctorReport`,
      parser de `security find-identity` (team id + revogados), checks injetáveis:
      Xcode, Signing, Devices, Developer Mode (por device), Port forwarding (iproxy),
      WDA build, WDA server. Render humano (checklist + "Next steps") + `--json`.
- [x] CLI `doctor [--udid] [--json]` agora é o preflight completo (exit 1 se há bloqueio).
      Avalia o estado e gera exatamente o que o usuário precisa fazer.

## Estado real da máquina (do doctor ao vivo)
- Xcode 26.5 OK; Signing OK (teams <ORPHAN_TEAM_ID> pessoal, <ORG_TEAM_ID> org); 1 device físico.
- Pendências p/ device: instalar `iproxy` (brew libimobiledevice); device só em rede (Wi-Fi).
- Developer Mode já habilitado no iPhone. Trust do cert: passo manual após 1ª instalação.

## Branch de device (free) — implementado e testado (e2e bloqueado em passo manual)
- [x] `SigningOptions`; patch idempotente do bundle id do Runner no `project.pbxproj`
      (Lib mantém `com.facebook.*`, só o Runner vira `com.lazyworker.wda.*`).
- [x] `WdaBuilder.build_device` (DEVELOPMENT_TEAM, -allowProvisioningUpdates, CODE_SIGN_STYLE).
- [x] `WdaLauncher.launch_device` (test-without-building -destination platform=iOS,id=).
- [x] `PortForwarder` (iproxy local:device), `RunState.forward_pid`,
      `BootstrapService.bootstrap(signing)/up_device/down` (mata iproxy + WDA).
- [x] CLI `bootstrap`/`up` ramificam por `SigningMode` (lê `lazyworker.toml`).
- [x] `iproxy` instalado (brew libimobiledevice). `lazyworker.toml` com mode=free, team <ORPHAN_TEAM_ID>.

## ACHADO importante (corrigido no doctor)
- O build de device falhou: `No Account for Team "<ORPHAN_TEAM_ID>"`. Causa: **nenhuma Apple ID
  logada no Xcode** (`IDEProvisioningTeams` ausente). Certificado no keychain != conta no Xcode.
- `doctor` agora cruza contas-do-Xcode (`com.apple.dt.Xcode.plist`) com certificados e
  flagra corretamente: "certificates present but no Apple ID in Xcode".

## Assinatura grátis VALIDADA (build de device ok)
- A Apple ID do usuário já estava logada no Xcode; team free correto = **<FREE_TEAM_ID>**
  (Personal Team da conta logada). O `<ORPHAN_TEAM_ID>` era cert órfão de outra identidade no keychain.
- Doctor corrigido: lê `IDEProvisioningTeamByIdentifier` (chave do Xcode 26) e valida que o
  `signing.team_id` do config existe nas contas do Xcode (lista os times free). Signing OK.
- `lazyworker bootstrap` (mode=free) buildou e assinou: app `...WebDriverAgentRunner.xctrunner`,
  TeamIdentifier <FREE_TEAM_ID>, cert "Apple Development" auto-criado pelo provisionamento.

## E2E EM DEVICE REAL — CONCLUÍDO (validado ao vivo)
- [x] `up --network`: lança WDA no iPhone, lê `ServerURLHere->http://IP:8100` do log,
      mira o IP direto (sem iproxy). RunState salvo com a URL do device.
- [x] Comandos de leitura (`status`/`source`/`doctor`) auto-miram o WDA ativo via `RunState`.
- [x] `doctor` ao vivo: WDA server ready no device; `source`/`tap` reais no iPhone (tela mudou).
- [x] `down` encerra (modo rede: forward_pid null, só mata o WDA). Estado limpo.
- Observações: trust do cert **não foi necessário** (Developer Mode ligado + launch via Mac
  confiável). `iproxy` 1.4 mudou sintaxe → corrigido p/ `iproxy LOCAL:DEVICE -u UDID`.
- [ ] Caminho USB (iproxy): sintaxe corrigida + testes unitários; falta validar ao vivo
      (pivotamos p/ rede a pedido). É só `lazyworker up` (sem --network) com cabo conectado.

## Interface agêntica de interação (`lazyworker ui`) — CONCLUÍDA (validada e2e)
- [x] Pacote `interaction/`: `OperationResult`/`ErrorCode`/`EXIT_CODES`, `Locator`+`LocatorResolver`
      (reusa `find_all`), `SnapshotSettings`/`SessionOptions`, `SessionState` (persiste a sessão do
      app em `~/.lazyworker/session.json`), `Interactor` (snapshot→resolve→gesto→status),
      `BatchRunner` (union discriminada de ops).
- [x] WDA: `create_session(wait_for_quiescence=False)`, `Session.apply_settings/double_tap/long_press`.
- [x] CLI sub-grupo `ui`: open/close/tree/tap/double-tap/long-press/scroll/scroll-to/type/screenshot/batch.
      Endereçamento por seletor (+`--index`) ou `--at`; `--dry-run`; saída JSON + exit codes determinísticos.
- [x] Agregação: `ui batch` (JSON via stdin/arquivo), stop-on-error, status por operação.
- [x] Heavy-app: sessão com quiescence off + snapshot settings (resolve o hang do WhatsApp/Chrome).
- [x] E2e ao vivo (simulador): open tunado → tap (ambiguidade com candidatos → desambígua por --type) →
      scroll → screenshot → batch (sucesso + stop-on-error) → close. 116 testes, ruff + mypy strict.

## App-laboratório SwiftUI + base e2e (`lab/`, `tests/e2e/`) — CONCLUÍDO
- [x] `lab/`: app SwiftUI mínimo, `.xcodeproj` escrito à mão (grupo sincronizado, sem dependência
      extra), bundle `com.lazyworker.lab`, iOS 16. Um único `event-log` (StaticText com
      `accessibilityIdentifier`) como fonte de verdade; string canônica por evento.
- [x] Labs cobrindo cada evento: tap, double-tap, long-press, toggle, type (+clear+secure),
      scroll, scroll-to (lista longa), screenshot, ambiguidade (botões gêmeos), combined + batch flow.
- [x] `tests/e2e/`: harness opt-in (LAZYWORKER_E2E=1) dirigindo o lab via CLI, asserções lendo o
      `event-log`. 12 casos, **todos passando ao vivo no simulador**.
- Achados (corrigidos no lab): tocar o centro de um `Toggle` cai no label → usar `labelsHidden`
  pro centro ser o switch; `onChange` sobrescrevia o evento de clear → unificado no `onChange`.
- Build: `xcodebuild -target ... CONFIGURATION_BUILD_DIR=...` (sem scheme); install via `simctl`.

## Próximos passos
- [ ] (Opcional) Validar o caminho USB+iproxy ao vivo.
- [ ] (Opcional) Validar o lab + e2e em device físico.
- [ ] Iniciar **Fase 1 (Exploração)** — base de interação agêntica + lab de validação prontos.
- [ ] Expor actions na CLI com gestão de sessão (reusar `RunState` / sessão ativa).
- [ ] Iniciar **Fase 1 (Exploração)** sobre a base agora funcional.
- [ ] Fechar as 3 decisões de arquitetura das fases (exploração LLM, Robots código vs dados).
- [ ] Desenhar formato/representação dos Robots.
- [ ] Detalhar Fase 3 (assertions) em momento separado.

## Decisões de fase ainda em aberto (device real)
- [ ] Apple ID grátis (refresh 7 dias, scriptável) vs. conta paga (anual). Define se há `resign` recorrente.
