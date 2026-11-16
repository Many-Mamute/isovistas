# Linguagem de especificação de peças (JSON)

Uma peça é uma lista de **features** aplicadas por ordem (somar ou cortar), mais as **vistas** a desenhar.

## Eixos e unidades
- **X** para a direita, **Y** para trás (profundidade), **Z** para cima. A vista de frente olha segundo +Y.
- Unidades em mm. Com `"u": 10`, todas as coordenadas e comprimentos estão em unidades do reticulado
  e são multiplicados por 10 (ângulos não).
- Escolhe a origem num canto ou eixo notável (por exemplo eixo de um cilindro principal, face inferior).

## Topo do ficheiro
```json
{"name": "Peça N", "u": 1,
 "meta": {"title": "Peça N", "author": "Nome", "number": "DT-01", "date": "2026-11-16",
          "sheet": "A3", "scale": "1:1"},
 "f": [ ...features... ],
 "views": [ ...opcional... ]}
```

## Features (`"t"`)
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

## Vistas (`views`, opcional; por omissão: frente, cima, esquerda)
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
