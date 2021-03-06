import torch

from .layer import FeaturesLinear, MultiLayerPerceptron, FeaturesEmbedding

class LSTM4FDModel(torch.nn.Module):
    """
    A pytorch implementation LSTM4FD
    Reference:
        Wang S, Liu C, Gao X, et al. Session-based fraud detection in online e-commerce transactions using recurrent neural networks[C]//Joint European Conference on Machine Learning and Knowledge Discovery in Databases. Springer, Cham, 2017: 241-252.
    """

    def __init__(self, field_dims, embed_dim, sequence_length, lstm_dims, mlp_dims, dropouts):
        super().__init__()
        self.embedding = FeaturesEmbedding(field_dims, embed_dim)
        self.src_embedding = FeaturesEmbedding(field_dims, embed_dim)
        self.tgt_embedding = FeaturesEmbedding(field_dims, embed_dim)

        self.linear = FeaturesLinear(field_dims)
        self.mlp = MultiLayerPerceptron(embed_dim + embed_dim, mlp_dims, dropouts[1])  # + hidden_size  + lstm_dims
        self.embed_dim = embed_dim

        self.src_domain_K = torch.nn.Linear(32, 32)
        self.src_domain_Q = torch.nn.Linear(32, 32)
        self.src_domain_V = torch.nn.Linear(32, 32)

        self.tgt_domain_K = torch.nn.Linear(32, 32)
        self.tgt_domain_Q = torch.nn.Linear(32, 32)
        self.tgt_domain_V = torch.nn.Linear(32, 32)

        self.lstm = torch.nn.LSTM(embed_dim, hidden_size=embed_dim, num_layers=1, batch_first=True, bidirectional=True)
        self.src_lstm = torch.nn.LSTM(embed_dim, hidden_size=embed_dim, num_layers=1, batch_first=True,
                                      bidirectional=True)
        self.tgt_lstm = torch.nn.LSTM(embed_dim, hidden_size=embed_dim, num_layers=1, batch_first=True,
                                      bidirectional=True)

    def forward(self, ids, values, seq_lengths, seq_mask, dlabel):
        """
        :param
        ids: the ids of fields (batch_size, seqlength, fields)
        values: the values of fields (batch_size, seqlength, fields)
        seq_length: the length of historical events (batch_size, 1)
        seq_mask: the attention mask for historical events (batch_size, seqlength)
        dlabel: the domain label of the batch samples (batch_size, 1)
        :return
        torch.sigmoid(result.squeeze(1)): the predition of the target payment
        term: the sequence embedding, output of user behavior extractor (batch_size, 32)
        """
        batch_size = ids.size()[0]
        if dlabel == 'src':
            shared_emb = self.embedding(ids, values)
            shared_t = torch.mean(shared_emb, 2)
            shared_history = shared_t[:, :-1, :]
            shared_term = shared_t[:, -1:, :].view(batch_size, -1)

            shared_pack = torch.nn.utils.rnn.pack_padded_sequence(shared_history, seq_lengths, batch_first=True,
                                                                  enforce_sorted=False)
            _, (shared_lstm_hn, __) = self.lstm(shared_pack)
            shared_lstm_hn = torch.mean(shared_lstm_hn, dim=0)

            shared_term = torch.cat((shared_lstm_hn, shared_term), 1)

            src_emb = self.src_embedding(ids, values)
            src_t = torch.mean(src_emb, 2)
            src_history = src_t[:, :-1, :]
            src_term = src_t[:, -1:, :].view(batch_size, -1)

            src_pack = torch.nn.utils.rnn.pack_padded_sequence(src_history, seq_lengths, batch_first=True,
                                                               enforce_sorted=False)
            _, (src_lstm_hn, __) = self.src_lstm(src_pack)
            src_lstm_hn = torch.mean(src_lstm_hn, dim=0)

            src_term = torch.cat((src_lstm_hn, src_term), 1)

            src_K = self.src_domain_K(src_term)
            src_Q = self.src_domain_Q(src_term)
            src_V = self.src_domain_V(src_term)
            src_a = torch.exp(torch.sum(src_K * src_Q, 1, True) / 7)

            shared_K = self.src_domain_K(shared_term)
            shared_Q = self.src_domain_Q(shared_term)
            shared_V = self.src_domain_V(shared_term)
            shared_a = torch.exp(torch.sum(shared_K * shared_Q, 1, True) / 7)

            term = src_a / (src_a + shared_a) * src_V + shared_a / (src_a + shared_a) * shared_V

            result = self.linear(ids[:, -1, :].view(batch_size, -1)) + self.mlp(term)
            return torch.sigmoid(result.squeeze(1)), term
        if dlabel == 'tgt':
            shared_emb = self.embedding(ids, values)
            shared_t = torch.mean(shared_emb, 2)
            shared_history = shared_t[:, :-1, :]
            shared_term = shared_t[:, -1:, :].view(batch_size, -1)

            shared_pack = torch.nn.utils.rnn.pack_padded_sequence(shared_history, seq_lengths, batch_first=True,
                                                                  enforce_sorted=False)
            _, (shared_lstm_hn, __) = self.lstm(shared_pack)
            shared_lstm_hn = torch.mean(shared_lstm_hn, dim=0)

            shared_term = torch.cat((shared_lstm_hn, shared_term), 1)

            tgt_emb = self.tgt_embedding(ids, values)
            tgt_t = torch.mean(tgt_emb, 2)
            tgt_history = tgt_t[:, :-1, :]
            tgt_term = tgt_t[:, -1:, :].view(batch_size, -1)

            tgt_pack = torch.nn.utils.rnn.pack_padded_sequence(tgt_history, seq_lengths, batch_first=True,
                                                               enforce_sorted=False)
            _, (tgt_lstm_hn, __) = self.tgt_lstm(tgt_pack)
            tgt_lstm_hn = torch.mean(tgt_lstm_hn, dim=0)

            tgt_term = torch.cat((tgt_lstm_hn, tgt_term), 1)

            tgt_K = self.tgt_domain_K(tgt_term)
            tgt_Q = self.tgt_domain_Q(tgt_term)
            tgt_V = self.tgt_domain_V(tgt_term)
            tgt_a = torch.exp(torch.sum(tgt_K * tgt_Q, 1, True) / 7)

            shared_K = self.tgt_domain_K(shared_term)
            shared_Q = self.tgt_domain_Q(shared_term)
            shared_V = self.tgt_domain_V(shared_term)
            shared_a = torch.exp(torch.sum(shared_K * shared_Q, 1, True) / 7)

            term = tgt_a / (tgt_a + shared_a) * tgt_V + shared_a / (tgt_a + shared_a) * shared_V

            result = self.linear(ids[:, -1, :].view(batch_size, -1)) + self.mlp(term)
            return torch.sigmoid(result.squeeze(1)), term
