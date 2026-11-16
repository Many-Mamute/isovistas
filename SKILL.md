---
name: desenho-tecnico-isovista
description: Converte uma peça desenhada em isométrico (imagem, screenshot ou foto de livro) num desenho ortográfico cotado segundo as normas ISO/FEUP, e o inverso (vistas para isométrico sobre reticulado), com verificação de ida-e-volta às cegas. Usar sempre que o pedido for desenho de vistas, cortes, cotagem nominal ou isométrico de uma peça.
---

# Desenho técnico: isométrico ⇄ vistas, com verificação de ida-e-volta

O trabalho divide-se em duas partes. Ler a imagem é o único passo caro: faz-se uma vez e escreve-se a
peça numa especificação JSON compacta. Tudo o resto (sólido exato, vistas, cortes, cotagem, folha,
comparações) é feito pela ferramenta `isovista` e devolve números, não imagens.

## Instalação (uma vez por sessão)
```bash
pip install -q "git+https://github.com/Many-Mamute/isovistas"   # ~1-2 min (build123d/OpenCascade)
```
Sem Python ou sem internet (ChatGPT ou Gemini gratuitos): escreve só o JSON e o utilizador corre o
notebook do Colab indicado no README do repositório.

## Regras para poupar tokens
1. A imagem enviada já está visível: não a voltes a abrir só para a ver.
2. No máximo 4 recortes ampliados para ler coordenadas, só nas zonas ambíguas (`isovista grid --crop`).
3. Nunca escrevas código de desenho, de cotagem ou de projeções: usa a CLI.
4. Verificações numéricas primeiro (`fit`, `compare`, lint do `draw`). Só olhas para uma imagem (uma vez,
   reduzida) quando um número falha e precisas de perceber porquê.
5. Corrige editando o JSON. Nunca reescrevas o ficheiro inteiro.
6. Corre `isovista dsl` antes de escrever a primeira especificação. Corre `isovista normas` só quando
   tiveres de escolher vistas ou cortes.

## Modo A: isométrico → vistas cotadas
**A0. Preparar a imagem.**
- Foto com perspetiva: `isovista rectify foto.jpg --quad x1,y1,...,x4,y4 --size L,A -o ret.png`
  (4 cantos de um retângulo conhecido no plano do papel, como a folha ou a moldura).
- Com reticulado: `isovista grid img.png --crop x0,y0,x1,y1 -o nos.png` dá um recorte com os nós
  rotulados (m,n), que é a ajuda visual para ler coordenadas.
- O enunciado diz quanto vale uma unidade do reticulado (normalmente 10 mm). Cotas escritas na figura
  têm prioridade sobre o reticulado.
- Uma miniatura com uma letra (por exemplo "V") e uma seta com a mesma letra mostra a peça vista nesse
  sentido. Serve para ler os elementos escondidos e não impõe a vista de frente.

**A1. Ler e escrever `peca.json`.**
- Usa `"u": 10` e coordenadas em unidades do reticulado (meias unidades são permitidas).
- Pensa por elementos: corpo base, cilindros, orelhas (`hull`), nervuras (`rib`), furos (`hole` com
  `cb`/`cs`), rasgos (`box` com `cut`), abas oblíquas (`ext` com plano geral).

**A2. Confirmar a leitura:**
```bash
isovista fit peca.json img.png --grid --pts '[[0,0,0,"15,23"],[6,0,0,"15,29"],[0,7,0,"8,23"],[0,0,6,"9,17"]]'
```
- Indica ≥ 4 pontos do modelo não coplanares, com o nó (m,n) do recorte ou o píxel (u,v).
- Dá `precision`: fração das arestas do modelo que estão desenhadas na figura. Tem de ser ≥ 0,95.
- Dá `worst`: zonas de tinta sem modelo. As cotas, o texto e os tracejados da figura também aparecem
  aqui, por isso olha para as coordenadas antes de mexer.
- Se falhar, acrescenta `--overlay ov.png` e olha uma vez para um recorte.

**A3. Escolher as vistas (☐ em `isovista normas`) e desenhar:**
```bash
isovista draw peca.json -o desenho            # SVG + PNG + PDF + JSON (com lint)
```
- O lint tem de vir vazio. Se indicar um texto que cruza linhas, uma vista fora da folha ou um eixo sem
  ligação, ajusta as vistas, a folha ou a escala no JSON.
- A cotagem é automática, completa e sem redundância por construção. Não acrescentes cotas à mão.

**A4. Ida-e-volta às cegas (obrigatória).** É o passo mais caro: usa um modelo mais pequeno (Sonnet ou
Haiku) e no máximo 4 recortes ampliados.
- Um contexto novo, sem acesso a `peca.json`, recebe só `desenho.png` e a saída de `isovista dsl` e escreve
  `inverso.json` com o PROMPT DE INVERSÃO abaixo.
- No Claude, usa um subagente com esse prompt. Noutras IAs, abre uma conversa nova com a imagem e o prompt.

**A5. Comparar:**
```bash
isovista compare peca.json inverso.json        # IoU ≥ 0,995 e nenhuma região diferente
isovista fit inverso.json img.png --grid --pts '...'   # o inverso também tem de bater com o original
```
- Se uma diferença aparece porque o desenho não define o elemento (falta uma cota, vista ou corte, ou
  há ambiguidade), corrige o desenho e repete A3–A5.
- Se o desenho define o elemento e o inverso o leu mal, regista isso como erro de leitura e não
  como erro do desenho.

**A6. Entregar** `desenho.pdf` e `desenho.svg`, com uma linha sobre o resultado da ida-e-volta.

## Modo B: vistas → isométrico
- **B0.** Retificar se for foto. Ler as cotas escritas: são elas que definem as medidas.
- **B1.** Escrever `peca.json` em mm.
- **B2.** Confirmar com `isovista fitviews peca.json vistas.png --views '[{"dir":"front","pts":[[x,y,z,u,v],...]}, ...]'`
  (≥ 3 pontos por vista; `precision` ≥ 0,93).
- **B3.** `isovista iso peca.json -o iso --unit 10` gera o isométrico sobre reticulado em A4.
  `--view fr|fl|br|bl` escolhe o lado observado.
- **B4.** Ida-e-volta às cegas: um contexto novo recebe só `iso.png` e a saída de `isovista dsl` e escreve `inverso.json`.
- **B5.** `isovista compare peca.json inverso.json`, e `fitviews` do inverso sobre o desenho original.

## PROMPT DE INVERSÃO (copiar tal como está, sem anexar o JSON original)
> Recebes apenas uma imagem de um desenho técnico e a especificação da linguagem JSON (dsl.md).
> Reconstrói a peça 3D só a partir do que o desenho mostra: cotas escritas, alinhamento entre vistas,
> tangências, simetrias e eixos. Não inventes valores. Quando algo não for dedutível, escolhe o mais
> plausível e regista-o em "assumptions". Escreve o JSON (lista "f") em inverso.json e valida-o com
> `isovista check inverso.json`. No fim, lista o que tiveste de assumir.

O que ficar em "assumptions" é o primeiro sítio onde procurar falhas do desenho.
