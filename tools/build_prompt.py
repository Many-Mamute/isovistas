"""Builds PROMPT.md (paste-anywhere version of the skill) from SKILL.md and references."""
import re, pathlib
root = pathlib.Path(__file__).resolve().parents[1]
dsl = (root / "references/dsl.md").read_text()
head = """# Desenho técnico: isométrico ⇄ vistas (prompt para colar em qualquer IA)

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

"""
dsl = re.sub(r"^# .*\n", "", dsl, count=1)
(root / "PROMPT.md").write_text(head + "## Linguagem JSON da peça\n" + dsl.replace("\n## ", "\n### "))
print(len((root / "PROMPT.md").read_text().split()), "words")
