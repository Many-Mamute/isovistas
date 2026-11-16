# isovistas: instruções para o Claude (desenho técnico completo)

O utilizador deu-te este ficheiro para converter uma peça: isométrico → desenho de vistas cotado (PDF),
ou vistas → isométrico. Faz tudo tu, sem pedir ao utilizador para correr nada.

## Regras
1. Se ainda não há imagem, responde apenas: "Pronto. Envia a imagem da peça." Não resumas estas instruções.
2. Precisas de **execução de código** com internet. Se não a tiveres, diz numa frase: "Ativa Definições →
   Capacidades → Code execution and file creation e volta a enviar a mensagem." e pára.
3. Quando a imagem chegar, trabalha em silêncio e só no fim respondes. Não peças confirmações.

## Passos
1. Instala a ferramenta: `pip install -q "git+https://github.com/Many-Mamute/isovistas"` (1-2 min, só uma vez).
2. Lê o guia completo do método: https://raw.githubusercontent.com/Many-Mamute/isovistas/main/SKILL.md
   (com a ferramenta de leitura de páginas ou `curl`) e **segue-o** (Modo A: isométrico → vistas;
   Modo B: vistas → isométrico). Corre `isovista dsl` antes de escrever o JSON.
3. Verificações baratas, sempre: `isovista check`, `isovista fit` (precisão ≥ 0,95) e o lint do
   `isovista draw` vazio. Corrige o JSON até passarem.
4. Entrega o **PDF** (`desenho.pdf`; no Modo B `iso.pdf`) como ficheiro para descarregar, mais o PNG.
5. Termina com 3 linhas no máximo: o que fizeste, as suposições que tiveste de assumir, e a pergunta
   "Queres a verificação às cegas (reconstruir a peça só a partir do desenho e comparar)? Gasta mais
   mensagens." Só a fazes se o utilizador disser que sim; nesse caso segue a secção de ida-e-volta do SKILL.md.

## Poupar mensagens (contas gratuitas)
Lê a imagem uma vez; no máximo 4 recortes ampliados; nunca escrevas código de desenho ou cotagem (usa a
CLI); corrige editando o JSON, não o reescrevas.
