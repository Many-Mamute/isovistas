# isovistas

## Usar só no Claude (sem instalar nada)
1. Em claude.ai → Definições → Capacidades, liga **Code execution and file creation**.
2. Cola numa conversa nova:
   `Lê https://raw.githubusercontent.com/Many-Mamute/isovistas/main/USAR_NO_CLAUDE.md e segue-o. Depois envio a imagem da peça.`
3. Envia a imagem da peça (screenshot ou foto). Recebes o desenho cotado em PDF.


Desenho técnico com IA: **isométrico ⇄ vistas ortográficas cotadas**, segundo as normas ISO usadas na
FEUP (ISO 128, 129-1, 5456-2, 5457, 7200, 3098). Funciona a partir de screenshots, PDFs ou fotos de livro.
Inclui uma **verificação de ida-e-volta às cegas**: o resultado é convertido de volta, sem acesso ao
original, e comparado com o original.

## Como funciona
1. **A IA lê a imagem uma vez** e descreve a peça num JSON curto (≈ 30 linhas). Ver `references/dsl.md`.
2. **A ferramenta faz o resto** sobre um sólido exato (OpenCascade):
   - vistas, cortes e vistas auxiliares;
   - linhas invisíveis e tracejados;
   - cotagem completa e sem redundância;
   - folha A3 com legenda ISO 7200;
   - isométrico sobre reticulado.
3. **Verificações numéricas**, sem gastar tokens com imagens:
   - `fit`: o modelo bate com a figura original?
   - `draw`: o lint deteta textos sobrepostos ou vistas fora da folha.
   - `compare`: a leitura às cegas do resultado é igual à peça original?

## Instalar
```bash
pip install "git+https://github.com/Many-Mamute/isovistas"
```
Requer Python ≥ 3.10. Instala `build123d` (OpenCascade), numpy, scipy, pillow e matplotlib.

## Usar com o Claude (recomendado)
Adiciona a pasta deste repositório como skill: as instruções estão em `SKILL.md`. Na prática, envias
a imagem e escreves "faz o desenho de vistas desta peça" ou "faz o isométrico destas vistas".

## Usar com qualquer IA (ChatGPT, Gemini, …), incluindo contas gratuitas
1. Cola o conteúdo de [`PROMPT.md`](PROMPT.md) numa conversa nova e envia a imagem.
2. A IA devolve o JSON da peça.
3. Abre o notebook [`notebooks/isovistas_colab.ipynb`](notebooks/isovistas_colab.ipynb) no Google Colab
   (gratuito), cola o JSON e corre as células. Recebes o PDF/PNG do desenho.
4. Para a ida-e-volta, abre outra conversa nova com o `PROMPT.md`, envia **só** a imagem gerada e pede o
   JSON. Cola-o na célula `compare` do notebook.

## Linha de comandos
```bash
isovista check  peca.json                                  # constrói e resume o sólido
isovista draw   peca.json -o desenho [--sheet A3 --scale 1:1]
isovista iso    peca.json -o iso [--unit 10 --view fr]
isovista grid   figura.png --crop x0,y0,x1,y1 -o nos.png  # nós (m,n) rotulados para ler coordenadas
isovista rectify foto.jpg --quad x1,y1,...,x4,y4 --size 297,210 -o ret.png
isovista fit    peca.json figura.png --grid --pts '[[0,0,0,"15,23"], ...]'
isovista fitviews peca.json vistas.png --views '[{"dir":"front","pts":[[x,y,z,u,v],...]}]'
isovista compare peca.json inverso.json
```

## Exemplo
`examples/peca_n.json` é uma peça com:
- corte por planos paralelos;
- nervuras não tracejadas;
- furos escareados e caixa cilíndrica;
- aba oblíqua com duas vistas auxiliares parciais.

Gera o desenho com `isovista draw examples/peca_n.json -o peca_n`.

## Limites conhecidos
- A escolha das vistas e dos cortes é feita por quem escreve o JSON. As regras estão em `references/normas.md`.
- A cotagem automática segue a teoria clássica e é completa, mas pode não coincidir cota a cota com a
  de um professor. Há várias cotagens corretas.
- Roscas, tolerâncias e estados de superfície ainda não são suportados.

Licença MIT.
