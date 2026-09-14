import { HttpClient } from '@angular/common/http';
import { Component, DestroyRef, effect, inject, input, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../app-config';

// GLPI guarda anexo/imagem como link pro documento (`document.send.php?
// docid=N`) — a tela não pode apontar `<img src>` direto pra lá (exige a
// sessão do GLPI, que não temos), então busca autenticado pelo nosso
// proxy (`server/ti/chamados.py::chamado_documento_route`) e troca pelo
// blob antes de renderizar.
const PADRAO_DOCID = /docid=(\d+)/;

const ATRIBUTOS_DE_LAYOUT = [
  'style',
  'width',
  'height',
  'bgcolor',
  'cellpadding',
  'cellspacing',
  'border',
  'align',
  'valign',
  'class',
  'role',
];

/** Renderiza `Chamado.descricao` (HTML bruto do GLPI) de um jeito
 * reutilizável nas telas de chamado. Um chamado aberto pelo portal normal
 * costuma vir com HTML simples (parágrafo, lista, imagem) e passa direto;
 * um chamado aberto por e-mail pode vir embrulhado na notificação inteira
 * do GLPI (tabela de layout pro Outlook, rodapé de assinatura, blocos de
 * "Acompanhamento" ecoando a própria notificação sem autor nem mensagem
 * real — confirmado ao vivo contra um chamado legado de um bug de loop de
 * e-mail já corrigido) — esse "embrulho" é limpo aqui antes de mostrar. */
@Component({
  selector: 'app-conteudo-chamado',
  imports: [],
  templateUrl: './conteudo-chamado.html',
  styleUrl: './conteudo-chamado.scss',
})
export class ConteudoChamado {
  private readonly http = inject(HttpClient);
  private readonly urlsDeObjeto: string[] = [];
  // Evita que uma resposta antiga (ex: imagem grande ainda carregando)
  // sobrescreva o conteúdo já trocado pra um chamado mais novo, se o
  // usuário abrir outro chamado antes da anterior terminar de processar.
  private geracaoAtual = 0;

  html = input('');

  protected readonly htmlProcessado = signal<string | null>(null);
  // >0 quando algum bloco de "Acompanhamento" vazio foi escondido — a tela
  // mostra um aviso discreto, senão o rodapé do próprio GLPI ("N° de
  // acompanhamentos: 7") não bate com nada visível e parece que sumiu
  // mensagem de verdade (confirmado com o usuário: gerava dúvida real).
  protected readonly acompanhamentosVaziosOcultados = signal(0);

  constructor() {
    effect(() => {
      this.processar(this.html());
    });

    inject(DestroyRef).onDestroy(() => {
      for (const url of this.urlsDeObjeto) {
        URL.revokeObjectURL(url);
      }
    });
  }

  private async processar(html: string): Promise<void> {
    const geracao = ++this.geracaoAtual;
    this.htmlProcessado.set(null);

    const raiz = new DOMParser().parseFromString(html, 'text/html').body;
    removerTagsIndesejadas(raiz);
    removerBoilerplateDeEmail(raiz);
    const acompanhamentosOcultados = removerAcompanhamentosVazios(raiz);
    despirAtributosDeLayout(raiz);
    await this.resolverImagens(raiz);

    if (geracao === this.geracaoAtual) {
      this.acompanhamentosVaziosOcultados.set(acompanhamentosOcultados);
      this.htmlProcessado.set(raiz.innerHTML);
    }
  }

  private async resolverImagens(raiz: HTMLElement): Promise<void> {
    await Promise.all(Array.from(raiz.querySelectorAll('img')).map((img) => this.resolverImagem(img)));
  }

  private async resolverImagem(img: HTMLImageElement): Promise<void> {
    const docid = PADRAO_DOCID.exec(img.getAttribute('src') ?? '')?.[1];
    if (!docid) {
      // Sem docid reconhecível (ex: logo do GLPI, ícone externo) — não dá
      // pra proxear; some com a imagem em vez de deixar o ícone quebrado.
      img.remove();
      return;
    }

    const blob = await new Promise<Blob | null>((resolver) => {
      this.http.get(`${MCP_API_BASE_URL}/api/ti/chamados/documentos/${docid}`, { responseType: 'blob' }).subscribe({
        next: (resposta) => resolver(resposta),
        error: () => resolver(null),
      });
    });

    if (blob === null) {
      img.remove();
      return;
    }
    const url = URL.createObjectURL(blob);
    this.urlsDeObjeto.push(url);
    img.setAttribute('src', url);
  }
}

function removerTagsIndesejadas(raiz: HTMLElement): void {
  raiz.querySelectorAll('style, script').forEach((elemento) => elemento.remove());
}

// GLPI acrescenta essa linha em todo chamado aberto por e-mail — instrução
// técnica de onde responder, sem conteúdo nenhum pro usuário.
function removerBoilerplateDeEmail(raiz: HTMLElement): void {
  Array.from(raiz.childNodes)
    .filter((no) => no.nodeType === Node.TEXT_NODE && (no.textContent ?? '').includes('Para responder por e-mail'))
    .forEach((no) => no.remove());
}

// Blocos de "Acompanhamento" que o GLPI ecoa na notificação por e-mail,
// mas sem autor nem mensagem real — mostrar "estruturado mesmo vazio" só
// seria ruído bonito (ver docstring do componente). Devolve quantos foram
// escondidos, pra tela avisar (sem isso, o rodapé do próprio GLPI, tipo
// "N° de acompanhamentos: 7", fica sem nenhum correspondente visível).
function removerAcompanhamentosVazios(raiz: HTMLElement): number {
  const vazios = Array.from(raiz.querySelectorAll('table'))
    // Só bloco-folha (sem tabela aninhada dentro) — o wrapper de layout que
    // ENVOLVE tanto o conteúdo real quanto os blocos de "Acompanhamento"
    // também tem "Acompanhamento" no textContent (herdado dos filhos);
    // sem esse filtro, o wrapper inteiro (conteúdo real incluído) era
    // removido junto — confirmado ao vivo contra o chamado #3272.
    .filter((tabela) => tabela.querySelectorAll('table').length === 0)
    .filter((tabela) => (tabela.textContent ?? '').includes('Acompanhamento'))
    .filter((tabela) => {
      const linhaAutor = Array.from(tabela.querySelectorAll('tr')).find((linha) =>
        (linha.textContent ?? '').includes('Autor'),
      );
      const valorAutor = linhaAutor?.querySelectorAll('td')[1]?.textContent?.trim();
      return !valorAutor;
    });
  vazios.forEach((tabela) => tabela.remove());
  return vazios.length;
}

// Remove atributo de apresentação (herdado de e-mail montado pro
// Outlook/Gmail) pra deixar o CSS do componente mandar no layout, em vez
// da tabela aninhada que o GLPI usa só pra compatibilidade de e-mail.
function despirAtributosDeLayout(raiz: HTMLElement): void {
  raiz.querySelectorAll('*').forEach((elemento) => {
    for (const atributo of ATRIBUTOS_DE_LAYOUT) {
      elemento.removeAttribute(atributo);
    }
  });
}
