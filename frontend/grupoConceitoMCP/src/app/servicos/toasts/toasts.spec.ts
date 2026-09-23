import { TestBed } from '@angular/core/testing';
import { Toasts } from './toasts';

describe('Toasts', () => {
  let servico: Toasts;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    servico = TestBed.inject(Toasts);
  });

  it('aviso() empilha um item do tipo "aviso" com a mensagem', () => {
    servico.aviso('Correção automática desativada nesse provedor.');

    expect(servico.itens()).toEqual([
      expect.objectContaining({
        tipo: 'aviso',
        mensagem: 'Correção automática desativada nesse provedor.',
      }),
    ]);
  });

  it('remover() tira o item da pilha pelo id', () => {
    servico.aviso('teste');
    const id = servico.itens()[0].id;

    servico.remover(id);

    expect(servico.itens()).toEqual([]);
  });
});
