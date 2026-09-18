import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { MCP_API_BASE_URL } from '../../app-config';
import { AnaliseCurriculo, Candidato, SituacaoAnalise } from './analise-curriculo';

const CANAL = 'agente-oracle-analise-curriculo';

// `BroadcastChannel` entrega mensagem de forma assíncrona (macrotask) mesmo
// entre duas instâncias no mesmo contexto de teste — sem esperar um tick,
// o `onmessage` ainda não rodou no momento da asserção.
const aguardarMensagem = () => new Promise((resolve) => setTimeout(resolve, 0));

const candidatoFake: Candidato & { situacao: SituacaoAnalise } = {
  id: 1,
  nome: 'Fulano de Tal',
  resumo_perfil: '',
  perfil_estruturado: {},
  status: 'ativo',
  criado_em: '2026-01-01T00:00:00Z',
  situacao: 'novo',
};

describe('AnaliseCurriculo — sincronização entre abas (BroadcastChannel)', () => {
  let httpMock: HttpTestingController;
  let servico: AnaliseCurriculo;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    httpMock = TestBed.inject(HttpTestingController);
    servico = TestBed.inject(AnaliseCurriculo);
  });

  afterEach(() => httpMock.verify());

  it('avisa outras abas (mesmo canal) quando inicia e conclui uma análise', async () => {
    const canalOutraAba = new BroadcastChannel(CANAL);
    const mensagens: unknown[] = [];
    canalOutraAba.onmessage = (evento) => mensagens.push(evento.data);

    const arquivo = new File(['conteudo'], 'curriculo.pdf', { type: 'application/pdf' });
    servico.iniciarAnalise(arquivo);
    await aguardarMensagem();

    const requisicao = httpMock.expectOne(`${MCP_API_BASE_URL}/api/rh/candidatos/analisar`);
    requisicao.flush(candidatoFake);
    await aguardarMensagem();

    expect(mensagens).toEqual([
      { tipo: 'iniciada', id: expect.any(String), nomeArquivo: 'curriculo.pdf' },
      { tipo: 'concluida', analiseId: expect.any(String), candidato: candidatoFake },
    ]);

    canalOutraAba.close();
  });

  it('avisa outras abas quando a análise falha', async () => {
    const canalOutraAba = new BroadcastChannel(CANAL);
    const mensagens: unknown[] = [];
    canalOutraAba.onmessage = (evento) => mensagens.push(evento.data);

    servico.iniciarAnalise(new File(['conteudo'], 'ilegivel.pdf'));
    await aguardarMensagem();

    const requisicao = httpMock.expectOne(`${MCP_API_BASE_URL}/api/rh/candidatos/analisar`);
    requisicao.flush({ erro: 'Currículo ilegível.' }, { status: 400, statusText: 'Bad Request' });
    await aguardarMensagem();

    expect(mensagens[1]).toMatchObject({ tipo: 'falhou', mensagem: 'Currículo ilegível.' });

    canalOutraAba.close();
  });

  it('reflete no próprio emAndamento/notificacoes o aviso recebido de outra aba', async () => {
    // Simula OUTRA aba postando no mesmo canal — o serviço sob teste só
    // recebe (nunca é o remetente, `BroadcastChannel` não entrega de volta
    // pro próprio remetente), então isso exercita exatamente o caminho de
    // "outra aba clicou em analisar, esta aba só escuta".
    const canalOutraAba = new BroadcastChannel(CANAL);

    canalOutraAba.postMessage({ tipo: 'iniciada', id: 'analise-remota-1', nomeArquivo: 'curriculo.pdf' });
    await aguardarMensagem();
    expect(servico.emAndamento()).toEqual([{ id: 'analise-remota-1', nomeArquivo: 'curriculo.pdf' }]);

    canalOutraAba.postMessage({ tipo: 'concluida', analiseId: 'analise-remota-1', candidato: candidatoFake });
    await aguardarMensagem();
    expect(servico.emAndamento()).toEqual([]);
    expect(servico.notificacoes()).toEqual([
      {
        id: `notif-${candidatoFake.id}`,
        candidatoId: candidatoFake.id,
        candidatoNome: candidatoFake.nome,
        situacao: candidatoFake.situacao,
        vista: false,
      },
    ]);
    expect(servico.candidatos()).toEqual([candidatoFake]);

    canalOutraAba.close();
  });
});
