# Regras de desenho técnico aplicadas (resumo FEUP / ISO)

Fontes: apontamentos de Desenho Técnico (J. S. Almacinha, FEUP): Normalização, Princípios gerais de
representação, Representação de dimensões e tolerâncias. A ferramenta já aplica tudo o que está marcado
com ✓. O que está marcado com ☐ é decisão de quem escreve a especificação (escolha de vistas e cortes).

## Folha e legenda
- ✓ Formatos ISO 5457 (A3 e maiores na horizontal). Esquadria com margem esquerda de 20 mm e
  restantes de 10 mm, traço de 0,7. Marcas de centragem. Designação do formato no canto inferior direito.
- ✓ Legenda ISO 7200 com 180 mm de largura, no canto inferior direito: departamento, referência técnica,
  tipo e estado do documento, proprietário legal, criado por, aprovado por, título, nº de identificação,
  revisão, data, língua, folha.
- ✓ Escala junto à legenda (ESCALA 1:1). Escalas recomendadas: 1:1, 1:2, 1:5, 1:10, 2:1, 5:1...
  Os valores das cotas são sempre os valores reais.
- ✓ Símbolo do método do 1.º diedro junto à legenda (tronco de cone, h=5 e H=10 com traço de 0,5).

## Linhas (ISO 128-2), grupo 0,7 / 0,35 (A3)
- ✓ Contínua grossa: arestas e contornos visíveis.
- ✓ Interrompida fina: arestas escondidas.
- ✓ Traço longo-ponto fino: eixos, linhas de simetria, linha do plano de corte.
- ✓ Contínua fina: cotas, linhas de chamada e de indicação, tracejados.
- ✓ Contínua fina ondulada: limite de vistas parciais.
- ✓ Prioridade em linhas coincidentes: visível, depois escondida, depois eixo.
- ✓ Escrita ISO 3098 tipo B direita, h = 3,5 mm; letras de vistas e cortes com h' = √2·h = 5 mm.

## Vistas (ISO 128-3, ISO 5456-2)
- ✓ Método do 1.º diedro: vista de cima por baixo da vista de frente, vista da esquerda à direita.
- ☐ A vista de frente é a mais esclarecedora (posição de funcionamento ou de fabrico).
- ☐ Número mínimo de vistas, suficiente para não haver ambiguidade. Evitar arestas escondidas e
  repetir detalhes. Preferir a vista com mais elementos visíveis.
- ☐ Cada plano inclinado deve aparecer projetante (reduzido a uma reta) numa das vistas.
- ☐ Cada superfície de revolução deve ter o eixo de topo numa das vistas.
- ☐ Faces oblíquas exigem vista auxiliar. Uma face oblíqua a todos os planos exige duas: a primária
  segundo a aresta do diedro (dá o ângulo em verdadeira grandeza) e a secundária perpendicular à face
  (dá a forma em verdadeira grandeza).
- ✓ Vistas auxiliares parciais com limite ondulado, em posição normal (alinhadas por projeção).
  Identificadas com uma letra repetida junto à seta (método das setas referenciadas).

## Cortes e secções
- ✓ Plano de corte: traço longo-ponto fino com as extremidades e as mudanças de direção a grosso.
  Setas grossas com letra direita. Corte identificado por "A-A" por cima da vista.
- ✓ Tracejado a 45° em traço fino, igual em todos os cortes da mesma peça. Nunca limitado por linhas escondidas.
- ✓ Nos cortes não se representam arestas escondidas.
- ✓ Cortes por planos paralelos: a mudança de plano não se representa quando não atravessa nenhuma aresta.
- ✓ Não se cortam longitudinalmente: nervuras, raios, veios, pinos, parafusos, chavetas (marcar com `rib`).
- ☐ Usar cortes quando há ocos interiores. Meio-corte para peças simétricas. Corte local para pequenos ocos.

## Cotagem (ISO 129-1, teoria clássica)
- ✓ Linha de cota e de chamada em traço fino. A chamada ultrapassa a linha de cota cerca de 8·d.
  Setas fechadas e cheias a 30°, com comprimento h.
- ✓ Valor a meio e ligeiramente acima da linha de cota, legível de baixo ou da direita. Nunca cruzado por linhas.
- ✓ Primeira linha de cota a cerca de 10 mm do contorno e as seguintes espaçadas de 7 mm (≥ 6 mm).
  Cotas curtas ficam por fora, com o texto ao lado.
- ✓ Cada elemento é cotado uma única vez. Sem cotas redundantes nem cadeias fechadas: a ferramenta
  usa uma árvore de cotas por eixo, o que garante que a cotagem é completa e não redundante.
- ✓ Cotas de atravancamento (dimensões totais) incluídas.
- ✓ Cotas de tamanho (dimensões das formas) e de situação (posição dos elementos) referidas a faces de
  referência, eixos ou planos de simetria. Planos de simetria e eixos de simetria não se cotam.
- ✓ Ø para arcos com mais de 180°, R para arcos de 180° ou menos. "n×" para elementos repetidos.
- ✓ Furos com nota: "n× Ø10 ⌵Ø15×90°" (escareado), "⌴Ø30 ↧10" (caixa cilíndrica), "↧12" (profundidade).
  Um furo único contido no plano de um corte é cotado no corte: Ø, Ø da caixa e profundidade.
- ✓ Os ângulos entre faces oblíquas e a peça são cotados na vista onde a aresta comum aparece de topo.
- ✓ Cotas dos elementos interiores no corte, dos exteriores nas vistas, cada uma na vista que mostra o
  elemento mais claramente.
