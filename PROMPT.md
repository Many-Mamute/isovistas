# Desenho técnico: isométrico ⇄ vistas (prompt para colar em qualquer IA)

## Regras de comportamento (lê primeiro)
- Se ainda não enviei imagem, responde apenas: "Pronto. Envia a imagem da peça." Não expliques nem resumas estas instruções.
- Quando enviar a imagem, a tua primeira resposta já é o JSON da peça. Não peças confirmações nem ofereças alternativas.
- A ferramenta `isovista draw` **gera sempre o PDF** (e SVG/PNG): `desenho.pdf`. Não digas que não está confirmado.
- Só prometes o PDF se **executaste** o comando e tens o ficheiro. Se não consegues instalar ou correr código, di-lo numa frase e entrega só o JSON com: "Cola-o em https://colab.research.google.com/github/Many-Mamute/isovistas/blob/main/notebooks/isovistas_colab.ipynb → Ambiente de execução → Executar tudo".
- Se puderes executar código com internet, pede-me autorização para instalar e depois faz tudo: instala, gera o PDF, verifica e entrega o ficheiro.

Vais ajudar-me a converter peças de desenho técnico: isométrico → vistas cotadas, ou vistas → isométrico.
A geometria, as vistas, a cotagem (normas ISO/FEUP) e as verificações são feitas pela ferramenta gratuita
**isovistas** (https://github.com/Many-Mamute/isovistas). Tu só lês a imagem e escreves a peça num JSON.

## O que fazes quando te envio uma imagem
1. Lês a peça **uma vez** com atenção:
   - reticulado isométrico: o enunciado diz quanto vale uma unidade (normalmente 10 mm);
   - cotas escritas: têm prioridade sobre o reticulado;
   - uma miniatura com uma letra e uma seta com a mesma letra mostram a peça vista nesse sentido
     (serve para ver o que está escondido).
2. Escreves **só** o JSON da peça, num bloco de código, segundo a linguagem abaixo. Usa `"u": 10` se
   leres coordenadas em unidades do reticulado.
3. Se for para fazer o desenho de vistas, acrescentas `"views"` com a vista de frente mais
   esclarecedora, o número mínimo de vistas e cortes onde houver ocos. Faces oblíquas levam vista
   auxiliar segundo a aresta comum e outra perpendicular à face. Marca as nervuras com `"rib": true`.
4. Depois do JSON, uma linha com o que assumiste por não estar definido na figura.

Se tiveres Python com internet: `pip install "git+https://github.com/Many-Mamute/isovistas"` e depois
`isovista draw peca.json -o desenho` (ou `isovista iso peca.json -o iso`) e `isovista compare a.json b.json`.
Se não tiveres: eu colo o teu JSON no notebook do Colab do repositório.

## Verificação de ida-e-volta (pedida numa conversa NOVA)
Quando te enviar só a imagem de um desenho gerado e escrever "INVERSO", reconstróis a peça apenas a
partir do que o desenho mostra: cotas, alinhamento entre vistas, tangências, simetrias e eixos. Não
inventes valores e regista em "assumptions" o que não for dedutível. Devolves o JSON. Eu comparo-o com
o original (`isovista compare`); diferenças indicam erros no desenho ou na leitura.

## Linguagem JSON da peça

Uma peça é uma lista de **features** aplicadas por ordem (somar ou cortar), mais as **vistas** a desenhar.

### Eixos e unidades
- **X** para a direita, **Y** para trás (profundidade), **Z** para cima. A vista de frente olha segundo +Y.
- Unidades em mm. Com `"u": 10`, todas as coordenadas e comprimentos estão em unidades do reticulado
  e são multiplicados por 10 (ângulos não).
- Escolhe a origem num canto ou eixo notável (por exemplo eixo de um cilindro principal, face inferior).

### Topo do ficheiro
```json
{"name": "Peça N", "u": 1,
 "meta": {"title": "Peça N", "author": "Nome", "number": "DT-01", "date": "2026-11-16",
          "sheet": "A3", "scale": "1:1"},
 "f": [ ...features... ],
 "views": [ ...opcional... ]}
```

### Features (`"t"`)
Chaves comuns: `"id"` (nome), `"cut": true` (remove material; por omissão soma), `"rib": true`
(nervura: não é tracejada em cortes longitudinais), `"mir": "x"` (acrescenta a cópia espelhada no plano
x=0; também `"xy"` ou `{"x": 35}`), `"at": [[x,y,z], ...]` (cópias noutros pontos, só translação).

| t | chaves | significado |
|---|---|---|
| `box` | `p` canto mínimo, `s` [dx,dy,dz] | paralelepípedo |
| `cyl` | `p` centro da base, `ax` eixo, `d` ou `r`, `h` | cilindro de `p` ao longo de `ax` |
| `cone` | `p`, `ax`, `d1` (base), `d2` (topo), `h` | tronco de cone |
| `sph` | `p`, `d` | esfera |
| `ext` | `pl`, `o`, `h`, `prof`, (`mid`) | extrusão de um perfil 2D |
| `rev` | `p`, `ax`, `prof` (coords r,h), `ang` | revolução |
| `hole` | `p` ponto de entrada, `ax` sentido para dentro, `d`, `depth` (omisso = passante), `cb` [D, prof], `cs` [D, ângulo], `tip` 118 | furo, caixa cilíndrica, escareado |

`ax`: `"x" "y" "z" "-x" "-y" "-z"` ou um vetor `[x,y,z]`.

### Planos de extrusão (`ext`)
- `"pl": "xy"`: perfil em (x,y), extrudido em +Z a partir de z=`o`, altura `h`.
- `"pl": "xz"`: perfil em (x,z), extrudido em +Y a partir de y=`o`.
- `"pl": "yz"`: perfil em (y,z), extrudido em +X a partir de x=`o`.
- Plano qualquer: `"pl": {"o":[x,y,z], "u":[..], "v":[..], "n":[..]}`. O perfil é dado em (u,v) a partir
  de `o`, e a extrusão segue `n` (por omissão u×v). Usa-o para abas e orelhas oblíquas.
- `h` negativo extrude no sentido oposto; `"mid": true` extrude simétrico.

### Perfis 2D (`prof`)
- `{"poly": [[x,y], [x,y,R], ...]}`: polígono fechado. `[x,y,R]` significa que o troço que chega a este
  ponto é um arco de raio |R| (R>0 centro à esquerda do sentido de percurso, R<0 à direita).
- `{"rect": [x0,y0,w,h]}`, `{"circ": [cx,cy,r]}`, `{"slot": [x1,y1,x2,y2,r]}` (rasgo oblongo).
- `{"hull": [{"circ":[..]}, {"pt":[x,y]}, ...]}`: envolvente convexa exata (tangentes reais). Ideal para
  orelhas: círculo da ponta + pontos da base.
- `{"u": [p1, p2, ...]}` união, `{"d": [p1, p2, ...]}` diferença (p1 menos os restantes).

### Vistas (`views`, opcional; por omissão: frente, cima, esquerda)
Método do 1.º diedro: cima fica por baixo da frente, esquerda fica à direita da frente.
```json
{"id":"A", "dir":"front", "label":"A",
 "cut":[{"n":"y","at":35,"if":[["x","<=",44]]}, {"n":"y","at":60,"if":[["x",">=",44]]}]}
{"id":"T", "dir":"top"}
{"id":"B", "dir":[1,2,0], "of":"T", "clip":[{"n":[2,-1,0],"op":"<=","p":[-40,25,60],"off":10}]}
```
- A primeira vista é a principal. `dir`: `front top left right bottom rear` ou um vetor (sentido de observação).
- `of`: vista a partir da qual esta é projetada (vistas auxiliares, por exemplo segundo uma aresta).
- `cut`: corte; cada passo é um plano ⟂ à direção de observação (`n` eixo/vetor, `at` coordenada ou
  `p` ponto). `if` limita o passo a uma região (cortes por planos paralelos). Meio-corte: dois passos,
  um deles fora da peça. As nervuras (`rib`) cortadas longitudinalmente não são tracejadas.
- `clip`: vista parcial; mantém `n·x op c` (c = `at`, ou `p` + `off`). O limite é desenhado a ondulado.
- `hid`: true/false (arestas invisíveis). Por omissão: sim nas vistas, não nos cortes.
- `label`: letra; as vistas auxiliares e os cortes recebem letras automaticamente.
- `at`: ponto 3D para onde aponta a seta da vista auxiliar.
